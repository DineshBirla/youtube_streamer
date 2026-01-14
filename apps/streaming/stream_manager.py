import subprocess
import os
import signal
import sys
import time
import logging
import requests
import tempfile
import threading
import json
from typing import Optional, Dict
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.apps import apps
from django.core.cache import cache
from django.db import transaction
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from celery import shared_task
import io

logger = logging.getLogger(__name__)

# ============ CONFIGURATION ============
TEMP_DIR = getattr(settings, 'STREAM_TEMP_DIR', '/var/tmp/streams')
MAX_CONCURRENT_DOWNLOADS = getattr(settings, 'MAX_CONCURRENT_DOWNLOADS', 3)
CHUNK_SIZE = 512 * 1024  # 512KB optimal for S3
STREAM_BUFFER_SIZE = '50M'
FFMPEG_TIMEOUT = 300  # 5min per operation
MAX_STREAM_RESTARTS = 5
CELERY_TASK_TIMEOUT = 86400  # 24 hours

# Ensure temp directory exists
Path(TEMP_DIR).mkdir(parents=True, exist_ok=True)


# ============ UTILITIES ============

class StreamCache:
    """Redis-backed cache for stream metadata"""
    
    @staticmethod
    def get_stream_key(stream_id):
        return f"stream:{stream_id}"
    
    @staticmethod
    def set_process_info(stream_id, pid, status):
        """Store process info in cache"""
        cache.set(
            StreamCache.get_stream_key(stream_id),
            {'pid': pid, 'status': status, 'started': datetime.now().isoformat()},
            timeout=86400
        )
    
    @staticmethod
    def get_process_info(stream_id):
        """Retrieve cached process info"""
        return cache.get(StreamCache.get_stream_key(stream_id)) or {}


def get_temp_dir_for_stream(stream_id):
    """Get unique temp directory per stream (prevents conflicts)"""
    stream_dir = os.path.join(TEMP_DIR, str(stream_id))
    Path(stream_dir).mkdir(parents=True, exist_ok=True)
    return stream_dir


def download_s3_file_chunked(media_file, stream_id):
    """Download S3 file with progress tracking"""
    url = media_file.file.url
    stream_dir = get_temp_dir_for_stream(stream_id)
    temp_path = os.path.join(stream_dir, f"media_{media_file.id}.mp4")
    
    try:
        resp = requests.get(url, stream=True, timeout=FFMPEG_TIMEOUT)
        resp.raise_for_status()
        
        total_size = int(resp.headers.get('content-length', 0))
        downloaded = 0
        
        with open(temp_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if total_size:
                        progress = (downloaded / total_size) * 100
                        logger.debug(f"Downloaded {media_file.title}: {progress:.1f}%")
        
        logger.info(f"✅ Downloaded {media_file.title} ({total_size / (1024**2):.1f}MB)")
        return temp_path
        
    except Exception as e:
        logger.error(f"Failed to download {media_file.title}: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


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
            logger.error(f"❌ Stream start failed: {e}", exc_info=True)
            self._set_error(str(e))
            self._cleanup_temp_files()
            return None
    
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
