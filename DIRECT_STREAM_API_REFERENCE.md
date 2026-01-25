# Direct Stream API Reference

## Overview

This document provides complete API reference and integration examples for the Direct Stream Playlist feature.

---

## Database Models

### Stream Model Updates

```python
from apps.streaming.models import Stream

# Available choices for streaming mode
PLAYLIST_SERVE_MODE_CHOICES = [
    ('download', 'Download Videos'),
    ('direct', 'Direct Stream (No Download)'),
]

class Stream(models.Model):
    # ... existing fields ...
    
    # New field for playlist streaming mode
    playlist_serve_mode = models.CharField(
        max_length=20,
        choices=PLAYLIST_SERVE_MODE_CHOICES,
        default='download',
        help_text='How to serve playlist videos: download or direct stream'
    )
```

---

## Backend API Methods

### StreamManager Class

#### 1. `_start_playlist_direct_stream()`

**Purpose:** Start direct streaming from YouTube playlist

**Signature:**
```python
def _start_playlist_direct_stream(self) -> Optional[int]
```

**Returns:**
- `int`: FFmpeg process ID (PID) on success
- `None`: On failure

**Example Usage:**
```python
from apps.streaming.stream_manager import StreamManager
from apps.streaming.models import Stream

stream = Stream.objects.get(id=stream_id)
manager = StreamManager(stream)

try:
    pid = manager._start_playlist_direct_stream()
    if pid:
        print(f"✅ Stream started: PID {pid}")
    else:
        print("❌ Failed to start stream")
except Exception as e:
    print(f"Error: {e}")
```

#### 2. `_get_playlist_video_urls()`

**Purpose:** Extract direct streaming URLs from YouTube playlist

**Signature:**
```python
def _get_playlist_video_urls(self) -> Dict[int, str]
```

**Returns:**
- `Dict[int, str]`: Mapping of video index to direct URL
  - Key: Video index (0, 1, 2, ...)
  - Value: Direct HTTPS URL (with signature and expiry)

**Example:**
```python
manager = StreamManager(stream)
video_urls = manager._get_playlist_video_urls()

# Result:
# {
#     0: 'https://youtube.com/stream/...?signature=xxx&expire=yyy',
#     1: 'https://youtube.com/stream/...?signature=xxx&expire=yyy',
#     2: 'https://youtube.com/stream/...?signature=xxx&expire=yyy',
# }

for idx, url in video_urls.items():
    print(f"Video {idx}: {url[:80]}...")
```

**Errors:**
- `Exception("No playlist selected")` - No playlist_id set
- `Exception("Failed to extract playlist videos")` - yt-dlp command failed
- `Exception("No videos found in playlist")` - Playlist is empty
- `Exception("Failed to extract any valid video URLs")` - All URLs invalid

#### 3. `_get_direct_video_url(video_id: str)`

**Purpose:** Get direct streaming URL for a single YouTube video

**Signature:**
```python
def _get_direct_video_url(self, video_id: str) -> Optional[str]
```

**Parameters:**
- `video_id` (str): YouTube video ID (e.g., "dQw4w9WgXcQ")

**Returns:**
- `str`: Direct HTTPS URL with signature
- `None`: If URL extraction fails

**Example:**
```python
manager = StreamManager(stream)

# Get URL for specific video
url = manager._get_direct_video_url("dQw4w9WgXcQ")

if url:
    print(f"Direct URL: {url}")
else:
    print("Failed to get URL")
```

#### 4. `_create_direct_concat_file(video_urls: Dict[int, str], loops: int = 50)`

**Purpose:** Create FFmpeg concat file with direct video URLs

**Signature:**
```python
def _create_direct_concat_file(
    self,
    video_urls: Dict[int, str],
    loops: int = 50
) -> str
```

**Parameters:**
- `video_urls`: Dictionary mapping index to direct URL
- `loops`: Number of times to loop through all videos (default: 50)

**Returns:**
- `str`: Path to generated concat file

**Concat File Format:**
```
file 'https://youtube.com/stream/url1?signature=xxx&expire=yyy'
file 'https://youtube.com/stream/url2?signature=xxx&expire=yyy'
...
file 'https://youtube.com/stream/url1?signature=xxx&expire=yyy'  # Loop 2
file 'https://youtube.com/stream/url2?signature=xxx&expire=yyy'
...
```

**Example:**
```python
video_urls = {
    0: 'https://youtube.com/stream/url1?...',
    1: 'https://youtube.com/stream/url2?...',
    2: 'https://youtube.com/stream/url3?...',
}

concat_path = manager._create_direct_concat_file(video_urls, loops=100)
print(f"Concat file created: {concat_path}")

# Read the file to verify
with open(concat_path, 'r') as f:
    print(f.read())
```

---

## Main Streaming Methods

### `start_ffmpeg_stream()`

**Updated Method - Now Routes Based on Serve Mode**

**Signature:**
```python
def start_ffmpeg_stream(self) -> Optional[int]
```

**Logic Flow:**
```
stream.stream_source == 'playlist' ?
    ├─ Yes: check stream.playlist_serve_mode
    │   ├─ 'direct' → _start_playlist_direct_stream()
    │   └─ 'download' → _start_playlist_stream()
    └─ No: _start_media_files_stream()
```

**Example:**
```python
from apps.streaming.stream_manager import StreamManager

stream = Stream.objects.get(id=stream_id)
manager = StreamManager(stream)

# Automatically routes to correct method based on configuration
pid = manager.start_ffmpeg_stream()

if pid:
    print(f"Stream started: PID {pid}")
    print(f"Status: {stream.status}")
else:
    print(f"Failed: {stream.error_message}")
```

---

## Views Integration

### `stream_create()` View

**Handles New Parameter:**

```python
# Extract from POST request
playlist_serve_mode = request.POST.get('playlist_serve_mode', 'download')

# Create stream with serve mode
stream = Stream.objects.create(
    user=request.user,
    youtube_account=youtube_account,
    title=title,
    stream_source=stream_source,
    playlist_id=playlist_id if stream_source == 'playlist' else '',
    playlist_serve_mode=playlist_serve_mode if stream_source == 'playlist' else 'download'
)
```

**Context Provided to Template:**

```python
context = {
    'youtube_accounts': youtube_accounts,
    'media_files': media_files,
    'storage_usage': '2.5 GB',
    'storage_limit': '100 GB',
    'storage_available': '97.5 GB',
    'playlist_serve_modes': [
        {'value': 'download', 'label': 'Download Videos'},
        {'value': 'direct', 'label': 'Direct Stream (No Download)'},
    ],
}
```

---

## CLI/Celery Integration

### Create and Start Direct Stream (Celery Task)

```python
from apps.streaming.models import Stream
from apps.streaming.stream_manager import StreamManager
from celery import shared_task

@shared_task
def create_and_start_direct_stream(user_id, youtube_account_id, playlist_id, title):
    """Create and start a direct stream via Celery"""
    from django.contrib.auth.models import User
    from apps.accounts.models import YouTubeAccount
    
    try:
        user = User.objects.get(id=user_id)
        youtube_account = YouTubeAccount.objects.get(
            id=youtube_account_id,
            user=user
        )
        
        # Create stream with direct mode
        stream = Stream.objects.create(
            user=user,
            youtube_account=youtube_account,
            title=title,
            stream_source='playlist',
            playlist_id=playlist_id,
            playlist_serve_mode='direct',  # Enable direct streaming
            shuffle_playlist=False,
            loop_enabled=True
        )
        
        # Start streaming
        manager = StreamManager(stream)
        pid = manager.start_ffmpeg_stream()
        
        if pid:
            return {
                'status': 'success',
                'stream_id': str(stream.id),
                'pid': pid,
                'message': f'Stream started: {title}'
            }
        else:
            return {
                'status': 'error',
                'stream_id': str(stream.id),
                'message': f'Failed to start stream: {stream.error_message}'
            }
            
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }

# Usage:
# create_and_start_direct_stream.delay(user_id=1, youtube_account_id=5, 
#                                      playlist_id='PLxxxxx', title='My Stream')
```

### Monitor Direct Stream Status

```python
@shared_task
def monitor_stream_status(stream_id):
    """Monitor and log stream status"""
    from apps.streaming.models import Stream, StreamLog
    from apps.streaming.stream_manager import StreamCache
    
    try:
        stream = Stream.objects.get(id=stream_id)
        process_info = StreamCache.get_process_info(stream_id)
        
        if not process_info:
            StreamLog.objects.create(
                stream=stream,
                level='WARNING',
                message='Stream process info not found in cache'
            )
            return False
        
        pid = process_info.get('pid')
        
        # Check if process is still running
        import os
        import signal
        try:
            os.kill(pid, 0)  # Signal 0 = check if process exists
            status = 'RUNNING'
        except OSError:
            status = 'STOPPED'
        
        StreamLog.objects.create(
            stream=stream,
            level='INFO',
            message=f'Stream status: {status} (PID: {pid})'
        )
        
        return status == 'RUNNING'
        
    except Stream.DoesNotExist:
        return False
```

---

## Python/Django Examples

### Complete Direct Stream Workflow

```python
from apps.streaming.models import Stream
from apps.streaming.stream_manager import StreamManager
from apps.accounts.models import YouTubeAccount
from django.contrib.auth.models import User

def create_direct_playlist_stream(user, youtube_account_id, playlist_id, 
                                   title, shuffle=False, loops=50):
    """
    Complete workflow to create and start a direct playlist stream
    
    Args:
        user: Django User object
        youtube_account_id: ID of connected YouTube account
        playlist_id: YouTube playlist ID (e.g., 'PLxxxxxx')
        title: Stream title
        shuffle: Whether to shuffle playlist videos
        loops: Number of times to loop through playlist
    
    Returns:
        dict: {
            'success': bool,
            'stream_id': str,
            'pid': int or None,
            'message': str,
            'details': dict
        }
    """
    try:
        # Step 1: Get YouTube account
        youtube_account = YouTubeAccount.objects.get(
            id=youtube_account_id,
            user=user,
            is_active=True
        )
        print(f"✓ YouTube account found: {youtube_account.channel_name}")
        
        # Step 2: Create stream object
        stream = Stream.objects.create(
            user=user,
            youtube_account=youtube_account,
            title=title,
            description=f"Direct playlist stream created via API",
            stream_source='playlist',
            playlist_id=playlist_id,
            playlist_serve_mode='direct',
            shuffle_playlist=shuffle,
            loop_enabled=True
        )
        print(f"✓ Stream created: {stream.id}")
        
        # Step 3: Initialize stream manager
        manager = StreamManager(stream)
        print(f"✓ StreamManager initialized")
        
        # Step 4: Start streaming
        pid = manager.start_ffmpeg_stream()
        
        if pid:
            return {
                'success': True,
                'stream_id': str(stream.id),
                'pid': pid,
                'message': f'Stream started successfully',
                'details': {
                    'title': stream.title,
                    'playlist_id': stream.playlist_id,
                    'mode': 'direct',
                    'shuffle': stream.shuffle_playlist,
                    'status': stream.status,
                    'process_id': stream.process_id
                }
            }
        else:
            return {
                'success': False,
                'stream_id': str(stream.id),
                'pid': None,
                'message': f'Failed to start stream',
                'details': {
                    'error': stream.error_message,
                    'status': stream.status
                }
            }
            
    except YouTubeAccount.DoesNotExist:
        return {
            'success': False,
            'stream_id': None,
            'pid': None,
            'message': 'YouTube account not found or not active'
        }
    except Exception as e:
        return {
            'success': False,
            'stream_id': None,
            'pid': None,
            'message': f'Error: {str(e)}'
        }

# Usage:
user = User.objects.get(username='john')
result = create_direct_playlist_stream(
    user=user,
    youtube_account_id=5,
    playlist_id='PLxxxxxxxxxxxxx',
    title='My 24/7 Music Stream',
    shuffle=True,
    loops=100
)

if result['success']:
    print(f"✅ Stream created and started!")
    print(f"   Stream ID: {result['stream_id']}")
    print(f"   Process ID: {result['pid']}")
else:
    print(f"❌ Error: {result['message']}")
```

### Query Stream by Mode

```python
# Get all direct streams (no download)
direct_streams = Stream.objects.filter(
    stream_source='playlist',
    playlist_serve_mode='direct'
)
print(f"Direct streams: {direct_streams.count()}")

# Get all download mode streams
download_streams = Stream.objects.filter(
    stream_source='playlist',
    playlist_serve_mode='download'
)
print(f"Download streams: {download_streams.count()}")

# Get running direct streams for a user
user_direct_streams = Stream.objects.filter(
    user=user,
    stream_source='playlist',
    playlist_serve_mode='direct',
    status='running'
)
print(f"User's active direct streams: {user_direct_streams.count()}")
```

### Stop Direct Stream

```python
from apps.streaming.stream_manager import StreamManager

stream = Stream.objects.get(id=stream_id)
manager = StreamManager(stream)

# Stop the stream
success = manager.stop_stream()

if success:
    print(f"✅ Stream stopped")
    print(f"   Status: {stream.status}")
    print(f"   Stopped at: {stream.stopped_at}")
else:
    print(f"❌ Failed to stop stream")
```

### Get Stream Logs

```python
from apps.streaming.models import StreamLog

stream = Stream.objects.get(id=stream_id)

# Get recent logs
recent_logs = stream.logs.all().order_by('-created_at')[:50]

for log in recent_logs:
    print(f"[{log.level}] {log.created_at.strftime('%H:%M:%S')} - {log.message}")

# Get errors only
error_logs = stream.logs.filter(level='ERROR').order_by('-created_at')[:20]
if error_logs:
    print("Recent errors:")
    for log in error_logs:
        print(f"  {log.message}")
```

---

## Error Handling

### Common Errors and Solutions

```python
from apps.streaming.stream_manager import StreamManager
from apps.streaming.models import Stream

stream = Stream.objects.get(id=stream_id)
manager = StreamManager(stream)

try:
    pid = manager.start_ffmpeg_stream()
    
except Exception as e:
    error_msg = str(e)
    
    # Handle specific errors
    if "No playlist selected" in error_msg:
        print("❌ Playlist ID not set")
        # Solution: Set stream.playlist_id
        
    elif "Failed to authenticate with YouTube" in error_msg:
        print("❌ YouTube authentication failed")
        # Solution: Refresh OAuth tokens
        
    elif "Failed to extract playlist videos" in error_msg:
        print("❌ Could not fetch playlist")
        # Solution: Check playlist is public and accessible
        
    elif "No videos found in playlist" in error_msg:
        print("❌ Playlist is empty")
        # Solution: Add videos to playlist
        
    elif "FFmpeg not found" in error_msg:
        print("❌ FFmpeg not installed")
        # Solution: Install FFmpeg on system
        
    elif "yt-dlp not found" in error_msg:
        print("❌ yt-dlp not installed")
        # Solution: pip install yt-dlp
        
    else:
        print(f"❌ Unexpected error: {error_msg}")
```

---

## Performance Metrics

### Startup Time Comparison

```python
import time
from apps.streaming.stream_manager import StreamManager

# Direct Stream startup
stream_direct = Stream.objects.create(
    playlist_serve_mode='direct',
    ...
)
manager_direct = StreamManager(stream_direct)

start = time.time()
pid = manager_direct.start_ffmpeg_stream()
direct_time = time.time() - start

# Download Mode startup
stream_download = Stream.objects.create(
    playlist_serve_mode='download',
    ...
)
manager_download = StreamManager(stream_download)

start = time.time()
pid = manager_download.start_ffmpeg_stream()
download_time = time.time() - start

print(f"Direct mode startup: {direct_time:.1f}s")
print(f"Download mode startup: {download_time:.1f}s")
print(f"Speedup: {download_time / direct_time:.1f}x faster")
```

---

## Summary

The Direct Stream API provides:

✅ **Simple Methods** - Few, focused functions for direct streaming  
✅ **Flexible Integration** - Works with Django views, Celery, or CLI  
✅ **Error Handling** - Clear exceptions and logging  
✅ **Performance** - Optimized for real-time streaming  
✅ **Backward Compatible** - Works alongside existing download mode  

**Key Methods:**
- `_start_playlist_direct_stream()` - Start streaming
- `_get_playlist_video_urls()` - Extract URLs
- `_get_direct_video_url(video_id)` - Single URL extraction
- `_create_direct_concat_file()` - Build FFmpeg concat file

**Use Direct Mode for:**
- Large playlists (100+ videos)
- No storage requirement
- Fast streaming setup
- Stable internet connections

Happy streaming! 🚀
