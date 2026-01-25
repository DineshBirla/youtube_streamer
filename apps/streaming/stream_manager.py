import subprocess
import os
import signal
import time
import logging
import logging.handlers
import requests
import json
from typing import Optional, Dict, List
from datetime import datetime, timedelta
from pathlib import Path
from functools import lru_cache
from urllib.parse import urlparse

from django.conf import settings
from django.apps import apps
from django.core.cache import cache
from django.db import transaction, connection
from django.db.utils import OperationalError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from celery import shared_task

# ============ LOGGING CONFIGURATION (optimized for production) ============
logger = logging.getLogger(__name__)
if not logger.handlers:
    # Use rotating file handler to prevent disk filling
    # For development, use a writable location; for production, configure STREAM_LOG_FILE
    log_file = getattr(settings, 'STREAM_LOG_FILE', './logs/stream.log')
    log_path = Path(log_file)
    
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        # Fallback to current directory if /var/log is not writable
        log_file = './logs/stream.log'
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
    
    handler = logging.handlers.RotatingFileHandler(
        filename=log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB per file
        backupCount=5
    )
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# ============ CONFIGURATION (cost-optimized defaults) ============
TEMP_DIR = getattr(settings, 'STREAM_TEMP_DIR', '/var/tmp/streams')
MAX_CONCURRENT_DOWNLOADS = getattr(settings, 'MAX_CONCURRENT_DOWNLOADS', 2)  # Reduced from 3
CHUNK_SIZE = getattr(settings, 'STREAM_CHUNK_SIZE', 256 * 1024)  # Reduced to 256KB for better memory
STREAM_BUFFER_SIZE = getattr(settings, 'STREAM_BUFFER_SIZE', '15M')  # Reduced from 50M for cost
FFMPEG_TIMEOUT = getattr(settings, 'FFMPEG_TIMEOUT', 300)
MAX_STREAM_RESTARTS = getattr(settings, 'MAX_STREAM_RESTARTS', 3)  # Reduced from 5
CELERY_TASK_TIMEOUT = getattr(settings, 'CELERY_TASK_TIMEOUT', 3600)  # 1hr, reduced from 24h
STREAM_CLEANUP_INTERVAL = getattr(settings, 'STREAM_CLEANUP_INTERVAL', 300)  # Cleanup every 5min
PROCESS_INFO_CACHE_TTL = 3600  # 1 hour, reduced from 24h

# Ensure temp directory exists
Path(TEMP_DIR).mkdir(parents=True, exist_ok=True)


# ============ UTILITIES ============

class StreamCache:
    """Redis-backed cache for stream metadata with TTL optimization"""
    
    CACHE_TTL = PROCESS_INFO_CACHE_TTL  # Use configured TTL
    KEY_PREFIX = "stream:"
    
    @staticmethod
    @lru_cache(maxsize=128)  # Local LRU cache for key generation
    def get_stream_key(stream_id):
        """Get cache key with local caching"""
        return f"{StreamCache.KEY_PREFIX}{stream_id}"
    
    @staticmethod
    def set_process_info(stream_id: int, pid: int, status: str) -> None:
        """Store process info in cache with TTL"""
        try:
            cache.set(
                StreamCache.get_stream_key(stream_id),
                {
                    'pid': pid,
                    'status': status,
                    'started': datetime.now().isoformat()
                },
                timeout=StreamCache.CACHE_TTL
            )
        except Exception as e:
            # Fail gracefully - logging only
            logger.warning(f"Cache set failed for stream {stream_id}: {e}")
    
    @staticmethod
    def get_process_info(stream_id: int) -> Dict:
        """Retrieve cached process info with fallback"""
        try:
            return cache.get(StreamCache.get_stream_key(stream_id)) or {}
        except Exception as e:
            logger.warning(f"Cache get failed for stream {stream_id}: {e}")
            return {}


def get_temp_dir_for_stream(stream_id):
    """Get unique temp directory per stream (prevents conflicts)"""
    stream_dir = os.path.join(TEMP_DIR, str(stream_id))
    Path(stream_dir).mkdir(parents=True, exist_ok=True)
    return stream_dir


def download_s3_file_chunked(media_file, stream_id: int, timeout: int = FFMPEG_TIMEOUT) -> Optional[str]:
    """Download S3 file with optimized chunking and connection pooling
    
    Args:
        media_file: MediaFile object to download
        stream_id: Stream ID for organizing temp files
        timeout: Request timeout in seconds
    
    Returns:
        Path to downloaded file or None if failed
    """
    url = media_file.file.url
    stream_dir = get_temp_dir_for_stream(stream_id)
    temp_path = os.path.join(stream_dir, f"media_{media_file.id}.mp4")
    
    try:
        # Use session for connection pooling (more efficient than individual requests)
        session = requests.Session()
        session.headers.update({'Connection': 'keep-alive'})
        
        resp = session.get(url, stream=True, timeout=timeout)
        resp.raise_for_status()
        
        total_size = int(resp.headers.get('content-length', 0))
        downloaded = 0
        last_log_time = time.time()
        
        with open(temp_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    # Log progress every 5 seconds (reduces I/O overhead)
                    if time.time() - last_log_time > 5:
                        if total_size:
                            progress = (downloaded / total_size) * 100
                            logger.debug(f"Download {media_file.title}: {progress:.1f}%")
                        last_log_time = time.time()
        
        file_size_mb = total_size / (1024 * 1024) if total_size else 0
        logger.info(f"Downloaded {media_file.title} ({file_size_mb:.1f}MB)")
        return temp_path
        
    except requests.exceptions.Timeout:
        logger.error(f"Download timeout for {media_file.title}")
        _safe_remove_file(temp_path)
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Download failed for {media_file.title}: {e}")
        _safe_remove_file(temp_path)
        return None
    except Exception as e:
        logger.error(f"Unexpected error downloading {media_file.title}: {e}")
        _safe_remove_file(temp_path)
        return None
    finally:
        session.close()


def _safe_remove_file(file_path: str) -> None:
    """Safely remove file without raising exception"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except OSError as e:
        logger.warning(f"Failed to remove {file_path}: {e}")


def download_files_parallel(media_files, stream_id):
    """Download multiple files concurrently using ThreadPoolExecutor"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    file_paths = {}
    
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOWNLOADS) as executor:
        futures = {
            executor.submit(download_s3_file_chunked, mf, stream_id): mf 
            for mf in media_files
        }
        
        for future in as_completed(futures):
            media_file = futures[future]
            try:
                file_path = future.result()
                file_paths[media_file.id] = file_path
            except Exception as e:
                logger.error(f"Download failed for {media_file.title}: {e}")
                raise
    
    return file_paths


def create_concat_file(media_files, file_paths, stream_id, loops=50):
    """Create FFmpeg concat demuxer file"""
    stream_dir = get_temp_dir_for_stream(stream_id)
    concat_path = os.path.join(stream_dir, 'concat.txt')
    
    with open(concat_path, 'w') as f:
        for loop in range(loops):
            for media_file in media_files:
                file_path = file_paths[media_file.id]
                # Escape special characters for FFmpeg
                f.write(f"file '{file_path}'\n")
    
    return concat_path


def resolve_ffmpeg_binary():
    """Resolve FFmpeg path with fallbacks"""
    paths = [
        os.getenv('FFMPEG_PATH'),
        '/usr/bin/ffmpeg',
        '/usr/local/bin/ffmpeg',
        'ffmpeg'
    ]
    
    for path in paths:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            logger.info(f"Using FFmpeg: {path}")
            return path
    
    raise RuntimeError("FFmpeg not found. Install: apt install ffmpeg")


# ============ STREAM MANAGER ============

class StreamManager:
    """Production-grade streaming manager with auto-restart & monitoring"""
    
    def __init__(self, stream):
        self.stream = stream
        self.youtube = None
        self.temp_dir = get_temp_dir_for_stream(stream.id)
        self.monitor_thread = None
        self.ffmpeg_process = None
    
    def authenticate_youtube(self) -> bool:
        """Authenticate with YouTube API"""
        try:
            yt_account = self.stream.youtube_account
            credentials = Credentials(
                token=yt_account.access_token,
                refresh_token=yt_account.refresh_token,
                token_uri='https://oauth2.googleapis.com/token',
                client_id=settings.GOOGLE_CLIENT_ID,
                client_secret=settings.GOOGLE_CLIENT_SECRET
            )
            self.youtube = build('youtube', 'v3', credentials=credentials)
            logger.info(f"✅ YouTube authenticated for {self.stream.id}")
            return True
        except Exception as e:
            logger.error(f"YouTube auth failed: {e}")
            return False
    
    def create_broadcast(self) -> Optional[str]:
        """Create YouTube live broadcast with thumbnail"""
        try:
            if not self.youtube and not self.authenticate_youtube():
                return None
            
            # Create broadcast
            broadcast_body = {
                'snippet': {
                    'title': self.stream.title,
                    'description': self.stream.description,
                    'scheduledStartTime': (datetime.utcnow() + timedelta(seconds=30)).isoformat() + 'Z'
                },
                'status': {
                    'privacyStatus': 'public',
                    'selfDeclaredMadeForKids': False
                },
                'contentDetails': {
                    'enableAutoStart': True,
                    'enableAutoStop': False,
                    'enableDvr': True,
                    'recordFromStart': True,
                }
            }
            
            broadcast = self.youtube.liveBroadcasts().insert(
                part='snippet,status,contentDetails',
                body=broadcast_body
            ).execute()
            
            broadcast_id = broadcast['id']
            logger.info(f"✅ Broadcast created: {broadcast_id}")
            
            # Upload thumbnail
            if self.stream.thumbnail:
                self._upload_thumbnail(broadcast_id)
            
            # Create stream
            stream_resp = self.youtube.liveStreams().insert(
                part='snippet,cdn,status',
                body={
                    'snippet': {'title': f"{self.stream.title} - Stream"},
                    'cdn': {
                        'frameRate': 'variable',
                        'ingestionType': 'rtmp',
                        'resolution': 'variable'
                    }
                }
            ).execute()
            
            stream_id = stream_resp['id']
            stream_key = stream_resp['cdn']['ingestionInfo']['streamName']
            ingestion_addr = stream_resp['cdn']['ingestionInfo']['ingestionAddress']
            
            # Bind broadcast to stream
            self.youtube.liveBroadcasts().bind(
                part='id,contentDetails',
                id=broadcast_id,
                streamId=stream_id
            ).execute()
            
            # Save to DB
            self.stream.broadcast_id = broadcast_id
            self.stream.stream_key = stream_key
            self.stream.stream_url = f"{ingestion_addr}/{stream_key}"
            self.stream.save()
            
            return broadcast_id
            
        except Exception as e:
            logger.error(f"Broadcast creation failed: {e}", exc_info=True)
            self._set_error(str(e))
            return None
    
    def _upload_thumbnail(self, broadcast_id):
        """Upload thumbnail to YouTube"""
        try:
            thumb_url = self.stream.thumbnail.url
            if not thumb_url.startswith('http'):
                thumb_url = f"https://{settings.AWS_S3_CUSTOM_DOMAIN}{thumb_url}"
            
            resp = requests.get(thumb_url, timeout=30)
            resp.raise_for_status()
            
            media = MediaIoBaseUpload(
                io.BytesIO(resp.content),
                mimetype='image/jpeg',
                resumable=True
            )
            
            self.youtube.thumbnails().set(
                videoId=broadcast_id,
                media_body=media
            ).execute()
            
            logger.info("✅ Thumbnail uploaded")
        except Exception as e:
            logger.warning(f"Thumbnail upload failed (non-critical): {e}")
    
    def start_ffmpeg_stream(self):
        """Start FFmpeg streaming - MAIN METHOD"""
        try:
            # Check stream source type
            if self.stream.stream_source == 'playlist':
                # Check if direct serve mode is enabled
                if hasattr(self.stream, 'playlist_serve_mode') and self.stream.playlist_serve_mode == 'direct':
                    return self._start_playlist_direct_stream()
                else:
                    return self._start_playlist_stream()
            else:
                return self._start_media_files_stream()
        except Exception as e:
            logger.error(f"❌ Stream start failed: {e}", exc_info=True)
            self._set_error(str(e))
            self._cleanup_temp_files()
            return None
    
    def _start_media_files_stream(self):
        """Start streaming from uploaded media files"""
        try:
            media_files = list(self.stream.media_files.all())
            if not media_files:
                raise Exception("No media files attached")
            
            logger.info(f"🚀 Starting stream {self.stream.id} with {len(media_files)} files")
            
            # Step 1: Download all files in parallel
            logger.info("⬇️ Downloading media files...")
            file_paths = download_files_parallel(media_files, self.stream.id)
            logger.info(f"✅ All {len(file_paths)} files downloaded")
            
            # Step 2: Create concat file
            concat_path = create_concat_file(media_files, file_paths, self.stream.id, loops=100)
            logger.info(f"✅ Concat file created: {concat_path}")
            
            # Step 3: Build FFmpeg command
            ffmpeg_cmd = self._build_ffmpeg_command(concat_path)
            
            # Step 4: Start FFmpeg
            self.ffmpeg_process = self._spawn_ffmpeg(ffmpeg_cmd)
            
            # Step 5: Start monitoring thread
            self._start_monitor_thread(ffmpeg_cmd)
            
            # Step 6: Update database
            self.stream.process_id = self.ffmpeg_process.pid
            self.stream.status = 'running'
            self.stream.started_at = datetime.now()
            self.stream.save()
            
            # Cache process info
            StreamCache.set_process_info(self.stream.id, self.ffmpeg_process.pid, 'running')
            
            logger.info(f"✅ Stream LIVE! PID: {self.ffmpeg_process.pid}")
            return self.ffmpeg_process.pid
            
        except Exception as e:
            logger.error(f"❌ Media files stream start failed: {e}", exc_info=True)
            self._set_error(str(e))
            self._cleanup_temp_files()
            return None
    
    def _start_playlist_stream(self):
        """Start streaming from YouTube playlist"""
        try:
            if not self.stream.playlist_id:
                raise Exception("No playlist selected")
            
            logger.info(f"🚀 Starting playlist stream {self.stream.id} from playlist {self.stream.playlist_id}")
            
            # Step 1: Download playlist videos
            logger.info("⬇️ Downloading playlist videos...")
            file_paths = self._download_playlist_videos()
            
            if not file_paths:
                raise Exception("Failed to download any videos from playlist")
            
            logger.info(f"✅ Downloaded {len(file_paths)} videos from playlist")
            
            # Step 2: Create concat file for playlist videos
            concat_path = self._create_playlist_concat_file(file_paths, loops=50)
            logger.info(f"✅ Concat file created: {concat_path}")
            
            # Step 3: Build FFmpeg command
            ffmpeg_cmd = self._build_ffmpeg_command(concat_path)
            
            # Step 4: Start FFmpeg
            self.ffmpeg_process = self._spawn_ffmpeg(ffmpeg_cmd)
            
            # Step 5: Start monitoring thread
            self._start_monitor_thread(ffmpeg_cmd)
            
            # Step 6: Update database
            self.stream.process_id = self.ffmpeg_process.pid
            self.stream.status = 'running'
            self.stream.started_at = datetime.now()
            self.stream.save()
            
            # Cache process info
            StreamCache.set_process_info(self.stream.id, self.ffmpeg_process.pid, 'running')
            
            logger.info(f"✅ Playlist Stream LIVE! PID: {self.ffmpeg_process.pid}")
            return self.ffmpeg_process.pid
            
        except Exception as e:
            logger.error(f"❌ Playlist stream start failed: {e}", exc_info=True)
            self._set_error(str(e))
            self._cleanup_temp_files()
            return None
    
    def _download_playlist_videos(self) -> Dict[int, str]:
        """Download all videos from YouTube playlist"""
        try:
            if not self.youtube and not self.authenticate_youtube():
                raise Exception("Failed to authenticate with YouTube")
            
            video_ids = self._get_playlist_video_ids()
            
            if not video_ids:
                raise Exception("No videos found in playlist")
            
            file_paths = {}
            stream_dir = self.temp_dir
            
            # Download videos sequentially to avoid rate limiting
            for idx, video_id in enumerate(video_ids):
                try:
                    logger.info(f"Downloading video {idx + 1}/{len(video_ids)}: {video_id}")
                    file_path = self._download_youtube_video(video_id, stream_dir, idx)
                    if file_path:
                        file_paths[idx] = file_path
                except Exception as e:
                    logger.warning(f"Failed to download video {video_id}: {e}")
                    continue
            
            return file_paths
            
        except Exception as e:
            logger.error(f"Failed to download playlist videos: {e}")
            raise
    
    def _get_playlist_video_ids(self) -> list:
        """Get all video IDs from YouTube playlist"""
        try:
            video_ids = []
            next_page_token = None
            
            while True:
                request = self.youtube.playlistItems().list(
                    part='contentDetails',
                    playlistId=self.stream.playlist_id,
                    maxResults=50,
                    pageToken=next_page_token
                )
                response = request.execute()
                
                for item in response.get('items', []):
                    video_id = item['contentDetails']['videoId']
                    video_ids.append(video_id)
                
                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break
            
            # Shuffle if enabled
            if self.stream.shuffle_playlist:
                import random
                random.shuffle(video_ids)
            
            logger.info(f"Found {len(video_ids)} videos in playlist")
            return video_ids
            
        except Exception as e:
            logger.error(f"Failed to get playlist video IDs: {e}")
            raise
    
    def _download_youtube_video(self, video_id: str, output_dir: str, index: int) -> Optional[str]:
        """Download a single YouTube video using yt-dlp"""
        try:
            import subprocess
            
            output_template = os.path.join(output_dir, f'video_{index:03d}.%(ext)s')
            
            # Use yt-dlp to download video
            cmd = [
                'yt-dlp',
                '-f', 'best[height<=720]/best',  # Best format up to 720p
                '-o', output_template,
                f'https://www.youtube.com/watch?v={video_id}'
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            
            if result.returncode != 0:
                logger.error(f"yt-dlp error: {result.stderr.decode()}")
                return None
            
            # Find the downloaded file
            for ext in ['mp4', 'mkv', 'webm', 'flv']:
                file_path = output_template.replace('%(ext)s', ext)
                if os.path.exists(file_path):
                    logger.info(f"✅ Downloaded: {file_path}")
                    return file_path
            
            logger.warning(f"No video file found for {video_id}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to download video {video_id}: {e}")
            return None
    
    def _create_playlist_concat_file(self, file_paths: Dict[int, str], loops: int = 50) -> str:
        """Create FFmpeg concat file for playlist videos"""
        concat_path = os.path.join(self.temp_dir, 'playlist_concat.txt')
        
        try:
            with open(concat_path, 'w') as f:
                for loop in range(loops):
                    for idx in sorted(file_paths.keys()):
                        file_path = file_paths[idx]
                        f.write(f"file '{file_path}'\n")
            
            logger.info(f"Created concat file: {concat_path}")
            return concat_path
            
        except Exception as e:
            logger.error(f"Failed to create concat file: {e}")
            raise
    
    def _start_playlist_direct_stream(self):
        """Start streaming directly from YouTube playlist URLs (no download)"""
        try:
            if not self.stream.playlist_id:
                raise Exception("No playlist selected")
            
            logger.info(f"🚀 Starting DIRECT playlist stream {self.stream.id} from playlist {self.stream.playlist_id}")
            
            # Step 1: Get video URLs from playlist
            logger.info("🔗 Extracting playlist video URLs...")
            video_urls = self._get_playlist_video_urls()
            
            if not video_urls:
                raise Exception("Failed to extract any video URLs from playlist")
            
            logger.info(f"✅ Extracted {len(video_urls)} video URLs from playlist")
            
            # Step 2: Create concat file for direct URLs
            concat_path = self._create_direct_concat_file(video_urls, loops=50)
            logger.info(f"✅ Concat file created: {concat_path}")
            
            # Step 3: Build FFmpeg command
            ffmpeg_cmd = self._build_ffmpeg_command(concat_path)
            
            # Step 4: Start FFmpeg
            self.ffmpeg_process = self._spawn_ffmpeg(ffmpeg_cmd)
            
            # Step 5: Start monitoring thread
            self._start_monitor_thread(ffmpeg_cmd)
            
            # Step 6: Update database
            self.stream.process_id = self.ffmpeg_process.pid
            self.stream.status = 'running'
            self.stream.started_at = datetime.now()
            self.stream.save()
            
            # Cache process info
            StreamCache.set_process_info(self.stream.id, self.ffmpeg_process.pid, 'running')
            
            logger.info(f"✅ Direct Playlist Stream LIVE! PID: {self.ffmpeg_process.pid}")
            return self.ffmpeg_process.pid
            
        except Exception as e:
            logger.error(f"❌ Direct playlist stream start failed: {e}", exc_info=True)
            self._set_error(str(e))
            self._cleanup_temp_files()
            return None
    
    def _get_playlist_video_urls(self) -> Dict[int, str]:
        """Extract direct video URLs from YouTube playlist using yt-dlp"""
        try:
            import subprocess
            
            video_urls = {}
            
            # Use yt-dlp to extract video URLs from playlist
            cmd = [
                'yt-dlp',
                '--flat-playlist',
                '--print', '%(id)s',
                f'https://www.youtube.com/playlist?list={self.stream.playlist_id}'
            ]
            
            logger.info(f"Extracting videos from playlist {self.stream.playlist_id}...")
            result = subprocess.run(cmd, capture_output=True, timeout=60)
            
            if result.returncode != 0:
                logger.error(f"yt-dlp error: {result.stderr.decode()}")
                raise Exception("Failed to extract playlist videos")
            
            video_ids = result.stdout.decode().strip().split('\n')
            video_ids = [vid for vid in video_ids if vid.strip()]
            
            if not video_ids:
                raise Exception("No videos found in playlist")
            
            logger.info(f"Found {len(video_ids)} videos in playlist")
            
            # Shuffle if enabled
            if self.stream.shuffle_playlist:
                import random
                random.shuffle(video_ids)
            
            # Extract direct streaming URL for each video
            for idx, video_id in enumerate(video_ids):
                try:
                    url = self._get_direct_video_url(video_id)
                    if url:
                        video_urls[idx] = url
                        logger.info(f"✅ Video {idx + 1}/{len(video_ids)}: {video_id} -> URL extracted")
                    else:
                        logger.warning(f"Failed to extract URL for video {idx + 1}: {video_id}")
                except Exception as e:
                    logger.warning(f"Error extracting URL for video {idx + 1}: {e}")
                    continue
            
            if not video_urls:
                raise Exception("Failed to extract any valid video URLs")
            
            logger.info(f"✅ Successfully extracted {len(video_urls)} direct video URLs")
            return video_urls
            
        except Exception as e:
            logger.error(f"Failed to get playlist video URLs: {e}")
            raise
    
    def _get_direct_video_url(self, video_id: str) -> Optional[str]:
        """Get direct streaming URL for a single YouTube video using yt-dlp"""
        try:
            import subprocess
            
            # Use yt-dlp to extract direct streaming URL
            cmd = [
                'yt-dlp',
                '-f', 'best[height<=720]/best',  # Best format up to 720p
                '--print', '%(url)s',
                '-g',  # Get URL only (don't download)
                f'https://www.youtube.com/watch?v={video_id}'
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            
            if result.returncode != 0:
                logger.error(f"Failed to get URL for {video_id}: {result.stderr.decode()}")
                return None
            
            url = result.stdout.decode().strip()
            if url and url.startswith('http'):
                logger.debug(f"Got direct URL for {video_id}")
                return url
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get direct URL for {video_id}: {e}")
            return None
    
    def _create_direct_concat_file(self, video_urls: Dict[int, str], loops: int = 50) -> str:
        """Create FFmpeg concat file for direct video URLs"""
        concat_path = os.path.join(self.temp_dir, 'direct_playlist_concat.txt')
        
        try:
            with open(concat_path, 'w') as f:
                for loop in range(loops):
                    for idx in sorted(video_urls.keys()):
                        url = video_urls[idx]
                        # Escape single quotes in URL
                        url_escaped = url.replace("'", "'\\''")
                        f.write(f"file '{url_escaped}'\n")
            
            logger.info(f"Created direct concat file: {concat_path}")
            return concat_path
            
        except Exception as e:
            logger.error(f"Failed to create direct concat file: {e}")
            raise
    
    def _build_ffmpeg_command(self, concat_path: str) -> list:
        """Build production-grade FFmpeg command"""
        ffmpeg_bin = resolve_ffmpeg_binary()
        
        return [
            ffmpeg_bin,
            
            # Input
            '-re',
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_path,
            
            # Video encoding - balanced for YouTube
            '-c:v', 'libx264',
            '-preset', 'veryfast',
            '-profile:v', 'main',
            '-level', '4.1',
            '-b:v', '3000k',
            '-maxrate', '4000k',
            '-bufsize', '8000k',
            '-g', '60',
            '-keyint_min', '60',
            '-pix_fmt', 'yuv420p',
            '-movflags', 'frag_keyframe+empty_moov',
            
            # Audio
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ar', '44100',
            '-ac', '2',
            
            # Output - FLV for RTMP
            '-f', 'flv',
            '-flvflags', 'no_duration_filesize',
            
            # Network settings
            '-rtbufsize', STREAM_BUFFER_SIZE,
            '-fflags', 'nobuffer',
            '-flags', 'low_delay',
            
            # Output URL
            self.stream.stream_url
        ]
    
    def _spawn_ffmpeg(self, cmd: list) -> subprocess.Popen:
        """Spawn FFmpeg process"""
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid,
                universal_newlines=True,
                bufsize=1
            )
            
            # Log FFmpeg output asynchronously
            threading.Thread(
                target=self._log_ffmpeg_output,
                args=(process.stderr,),
                daemon=True
            ).start()
            
            logger.info(f"FFmpeg spawned: PID {process.pid}")
            return process
            
        except Exception as e:
            logger.error(f"Failed to spawn FFmpeg: {e}")
            raise
    
    def _log_ffmpeg_output(self, stderr):
        """Log FFmpeg stderr in real-time"""
        try:
            for line in iter(stderr.readline, ''):
                if line:
                    logger.info(f"FFmpeg: {line.strip()}")
        except:
            pass
    
    def _start_monitor_thread(self, cmd: list):
        """Start monitoring thread for auto-restart"""
        self.monitor_thread = threading.Thread(
            target=self._monitor_ffmpeg,
            args=(cmd,),
            daemon=True
        )
        self.monitor_thread.start()
    
    def _monitor_ffmpeg(self, cmd: list):
        """Monitor FFmpeg and auto-restart on failure"""
        restarts = 0
        current_proc = self.ffmpeg_process
        
        while restarts < MAX_STREAM_RESTARTS:
            ret = current_proc.wait()
            logger.warning(f"FFmpeg exited (code={ret}), restart #{restarts}")
            
            if ret == 0:  # Clean exit
                break
            
            restarts += 1
            backoff = min(60, 5 * restarts)
            logger.info(f"Restarting in {backoff}s...")
            time.sleep(backoff)
            
            try:
                current_proc = self._spawn_ffmpeg(cmd)
                self.stream.process_id = current_proc.pid
                self.stream.status = 'running'
                self.stream.save()
                
                StreamCache.set_process_info(self.stream.id, current_proc.pid, 'running')
                logger.info(f"Restarted: New PID {current_proc.pid}")
                
            except Exception as e:
                logger.error(f"Restart failed: {e}")
                break
        
        # Final cleanup
        self._finalize_stream(restarts)
    
    def _finalize_stream(self, restarts: int):
        """Clean up after stream ends"""
        try:
            self.stream.process_id = None
            self.stream.status = 'error' if restarts >= MAX_STREAM_RESTARTS else 'stopped'
            self.stream.error_message = f'FFmpeg failed after {restarts} restarts'
            self.stream.stopped_at = datetime.now()
            self.stream.save()
            
            cache.delete(StreamCache.get_stream_key(self.stream.id))
            self._cleanup_temp_files()
            
            logger.info(f"Stream {self.stream.id} finalized")
        except Exception as e:
            logger.error(f"Finalization failed: {e}")
    
    def _cleanup_temp_files(self):
        """Remove temporary files"""
        try:
            import shutil
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"Cleaned up: {self.temp_dir}")
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")
    
    def _set_error(self, error_msg: str):
        """Set stream error state"""
        self.stream.status = 'error'
        self.stream.error_message = error_msg
        self.stream.save()
    
    def stop_stream(self) -> bool:
        """Stop stream gracefully"""
        try:
            # Kill FFmpeg
            if self.stream.process_id:
                try:
                    os.killpg(os.getpgid(self.stream.process_id), signal.SIGTERM)
                    time.sleep(2)
                    os.killpg(os.getpgid(self.stream.process_id), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            
            # End YouTube broadcast
            if self.youtube and self.stream.broadcast_id:
                try:
                    self.youtube.liveBroadcasts().transition(
                        broadcastStatus='complete',
                        id=self.stream.broadcast_id,
                        part='status'
                    ).execute()
                except Exception as e:
                    logger.warning(f"YouTube broadcast end failed: {e}")
            
            # Update database
            self.stream.status = 'stopped'
            self.stream.stopped_at = datetime.now()
            self.stream.process_id = None
            self.stream.save()
            
            # Cleanup
            self._cleanup_temp_files()
            
            logger.info(f"Stream {self.stream.id} stopped")
            return True
            
        except Exception as e:
            logger.error(f"Stop failed: {e}")
            return False


# ============ CELERY TASKS ============

@shared_task(
    time_limit=CELERY_TASK_TIMEOUT,
    soft_time_limit=CELERY_TASK_TIMEOUT - 300,
    acks_late=True,
    reject_on_worker_lost=True
)
def start_stream_task(stream_id: int):
    """Celery task to start stream"""
    try:
        Stream = apps.get_model('streaming', 'Stream')
        stream = Stream.objects.get(pk=stream_id)
        
        manager = StreamManager(stream)
        return manager.start_ffmpeg_stream()
        
    except Stream.DoesNotExist:
        logger.error(f"Stream {stream_id} not found")
        raise
    except Exception as e:
        logger.error(f"Stream task failed: {e}", exc_info=True)
        raise


@shared_task
def stop_stream_task(stream_id: int):
    """Celery task to stop stream"""
    try:
        Stream = apps.get_model('streaming', 'Stream')
        stream = Stream.objects.get(pk=stream_id)
        
        manager = StreamManager(stream)
        return manager.stop_stream()
        
    except Exception as e:
        logger.error(f"Stop task failed: {e}")
        return False
