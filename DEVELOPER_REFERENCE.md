# Playlist Streaming Feature - Developer Quick Reference

## 🎯 Feature Overview
Users can now stream from two sources:
1. **Uploaded Media Files** (existing)
2. **YouTube Playlists** (new)

---

## 📁 File Map

### Core Application Files
```
apps/streaming/
├── models.py              # Added: stream_source, playlist_id, playlist_title, shuffle_playlist
├── views.py               # Updated: stream_create(), Added: get_playlists_api()
├── urls.py                # Added: /api/playlists/ endpoint
├── stream_manager.py      # Added: 7 new methods for playlist handling
├── migrations/
│   └── 0001_add_playlist_streaming_fields.py  # New migration
```

### Template Files
```
templates/streaming/
├── stream_create.html     # Added: source selection, playlist UI
└── stream_detail.html     # Added: stream source badge, playlist info section
```

---

## 🔌 API Endpoints

### Get Playlists
**Endpoint:** `GET /streaming/api/playlists/`

**Parameters:**
```
youtube_account_id (required) - ID of YouTube account
```

**Response:**
```json
{
  "status": "success",
  "playlists": [
    {
      "id": "PLxxxxx",
      "title": "My Playlist",
      "item_count": 25,
      "thumbnail": "https://..."
    }
  ]
}
```

---

## 💾 Database Schema

### New Stream Model Fields
```python
stream_source = CharField(
    choices=[('media_files', 'Media Files'), ('playlist', 'YouTube Playlist')],
    default='media_files'
)
playlist_id = CharField(max_length=255, blank=True)
playlist_title = CharField(max_length=255, blank=True)
shuffle_playlist = BooleanField(default=False)
```

---

## 🏗️ Stream Manager Methods

### Public Methods
```python
start_ffmpeg_stream()  # Routes to appropriate streaming method
stop_stream()          # Stops any type of stream
create_broadcast()     # Creates YouTube broadcast
```

### Playlist-Specific Methods
```python
_start_playlist_stream()        # Main playlist streaming method
_download_playlist_videos()     # Downloads all playlist videos
_get_playlist_video_ids()       # Gets video IDs with shuffle support
_download_youtube_video()       # Downloads single video via yt-dlp
_create_playlist_concat_file()  # Creates FFmpeg concat file
```

---

## 🔄 Stream Creation Flow

### Media Files Flow
```
1. User selects "Media Files" source
2. Selects media files from library
3. Form submitted with stream_source='media_files'
4. Stream object created
5. media_files added to Stream.media_files
```

### Playlist Flow
```
1. User selects "Playlist" source
2. System loads playlists via API
3. User selects a playlist
4. Form submitted with stream_source='playlist'
5. Stream object created with playlist_id
6. stream.playlist_id is set
7. stream.shuffle_playlist set if enabled
```

---

## ▶️ Stream Start Flow

### For Media Files
```
StreamManager.start_ffmpeg_stream()
  → _start_media_files_stream()
    → download_files_parallel()
    → create_concat_file()
    → _build_ffmpeg_command()
    → _spawn_ffmpeg()
    → _start_monitor_thread()
```

### For Playlist
```
StreamManager.start_ffmpeg_stream()
  → _start_playlist_stream()
    → _download_playlist_videos()
      → _get_playlist_video_ids()
      → _download_youtube_video() [for each video]
    → _create_playlist_concat_file()
    → _build_ffmpeg_command()
    → _spawn_ffmpeg()
    → _start_monitor_thread()
```

---

## 🎨 Template Components

### stream_create.html
```html
<!-- Source Selection -->
<div class="source-selection">
  <input type="radio" name="stream_source" value="media_files" />
  <input type="radio" name="stream_source" value="playlist" />
</div>

<!-- Media Files Section -->
<div id="mediaFilesSection" class="source-content active">
  <!-- Media file checkboxes -->
</div>

<!-- Playlist Section -->
<div id="playlistSection" class="source-content">
  <!-- Playlist grid with radio buttons -->
</div>

<!-- Hidden Playlist ID Input -->
<input type="hidden" name="playlist_id" id="playlist_id" />
```

### stream_detail.html
```html
<!-- Conditional Display -->
{% if stream.stream_source == 'media_files' %}
  <!-- Show media files section -->
{% else %}
  <!-- Show playlist section -->
{% endif %}
```

---

## 🔧 Configuration

### Environment Variables (if any)
```bash
# Consider adding for customization
STREAM_DOWNLOAD_QUALITY=720  # Max video quality for playlist downloads
MAX_PLAYLIST_SIZE=100        # Max videos per playlist
STREAM_TEMP_DIR=/var/tmp/streams/
```

---

## 📊 Dependencies

### Python Packages
- `yt-dlp` - YouTube video downloading
- `google-auth-oauthlib` - YouTube OAuth (existing)
- `googleapiclient` - YouTube API (existing)

### System Tools
- `ffmpeg` - Video encoding and streaming
- `ffprobe` - Video analysis (included with ffmpeg)

---

## 🧪 Testing Checklist

```
□ Media file streaming still works
□ Create stream with playlist
□ Playlist selection loads correctly
□ Shuffle toggle works
□ Shuffle actually randomizes videos
□ Stream starts successfully
□ Videos download to correct temp directory
□ Stream detail shows correct source
□ Playlist info displays in detail page
□ Loop setting works with playlists
□ Error handling for unavailable videos
□ Error handling for no internet connection
□ Temp files cleanup after stream stops
□ Multiple streams run in parallel
```

---

## 📝 Logging

All operations logged to:
```
Logger: __name__ (streaming app)
Levels: DEBUG, INFO, WARNING, ERROR
```

Key log messages:
```
"✅ Found {n} videos in playlist"
"⬇️ Downloading playlist videos..."
"✅ Downloaded {n} videos from playlist"
"🚀 Starting playlist stream"
"FFmpeg: ..." (FFmpeg output)
"❌ Playlist stream start failed: {error}"
```

---

## 🐛 Debugging Tips

### Enable Debug Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check Temporary Files
```bash
ls -lah /var/tmp/streams/
# View specific stream files
ls -lah /var/tmp/streams/{stream_id}/
```

### Monitor FFmpeg Process
```bash
ps aux | grep ffmpeg
# Kill specific process
kill {pid}
```

### Test YouTube API
```python
from googleapiclient.discovery import build
# Test playlist list endpoint
youtube.playlists().list(part='snippet', mine=True).execute()
```

---

## 🔐 Security Considerations

1. **Playlist Visibility**: Only user's own playlists are accessible
2. **Video Access**: Only videos user has permission to access
3. **Temporary Storage**: Files deleted after streaming
4. **OAuth Scope**: Uses authenticated YouTube account

---

## 📈 Performance Notes

- **Parallel Downloads** (Media): Up to 3 concurrent downloads
- **Sequential Downloads** (Playlist): One at a time to avoid rate limiting
- **Temp Storage**: `/var/tmp/streams/{stream_id}/` for fast I/O
- **Cleanup**: Automatic after stream completion
- **FFmpeg Buffer**: 50M for streaming

---

## 🚨 Known Limitations

1. Max 100 playlists per account (API pagination limit)
2. Videos must be publicly accessible or user-accessible
3. No private/unlisted video support
4. Sequential download means slower start for large playlists
5. Quality capped at 720p (configurable)

---

## 🔮 Future Enhancements

```python
# Possible additions:
class PlaylistCache(models.Model):
    """Cache recently downloaded playlist info"""
    
class StreamQualityPreference(models.Model):
    """User quality preferences for playlists"""
    
class PlaylistMetrics(models.Model):
    """Track playlist streaming statistics"""
```

---

## 📞 Quick Commands

```bash
# Run migrations
python manage.py migrate streaming

# Create test data
python manage.py shell

# Test YouTube API connection
python manage.py shell
>>> from apps.accounts.models import YouTubeAccount
>>> account = YouTubeAccount.objects.first()
>>> # Test API access

# Check FFmpeg installation
ffmpeg -version

# Check yt-dlp installation
yt-dlp --version

# View stream logs
tail -f logs/django.log | grep streaming
```

---

## 🎓 Learning Resources

- **Stream Manager Logic**: `apps/streaming/stream_manager.py:167-270`
- **API Endpoint**: `apps/streaming/views.py:280-340`
- **Frontend Logic**: `templates/streaming/stream_create.html:900-950`
- **Form Validation**: `templates/streaming/stream_create.html:920-980`
