# Playlist Streaming Feature - Implementation Checklist

## ✅ Completed Changes

### 1. Database Models
- [x] Added `stream_source` field to Stream model
- [x] Added `playlist_id` field to Stream model  
- [x] Added `playlist_title` field to Stream model
- [x] Added `shuffle_playlist` field to Stream model
- [x] Updated `media_files` field to allow blank=True

### 2. Stream Manager
- [x] Updated `start_ffmpeg_stream()` to handle both sources
- [x] Created `_start_media_files_stream()` for media file streaming
- [x] Created `_start_playlist_stream()` for playlist streaming
- [x] Created `_download_playlist_videos()` to fetch playlist videos
- [x] Created `_get_playlist_video_ids()` to get video IDs with shuffle support
- [x] Created `_download_youtube_video()` using yt-dlp
- [x] Created `_create_playlist_concat_file()` for FFmpeg

### 3. Views
- [x] Updated `stream_create()` to handle playlist streams
- [x] Added form validation for both source types
- [x] Created `get_playlists_api()` endpoint
- [x] Added logger import

### 4. URLs
- [x] Added `/api/playlists/` endpoint

### 5. Templates - stream_create.html
- [x] Added source selection UI (radio buttons)
- [x] Added stream source section with two options
- [x] Updated media files section with conditional display
- [x] Added playlist section with:
  - [x] Playlist grid layout
  - [x] Playlist card styling
  - [x] Shuffle toggle
- [x] Updated JavaScript for source switching
- [x] Added `onStreamSourceChange()` function
- [x] Added `onYouTubeAccountChange()` function
- [x] Added `loadPlaylists()` function
- [x] Added `selectPlaylist()` function
- [x] Added `validateFormSubmit()` function

### 6. Templates - stream_detail.html
- [x] Added Stream Source badge in info table
- [x] Made Media Files section conditional
- [x] Added Playlist Information section for playlist streams
- [x] Styled playlist info display

### 7. Database Migration
- [x] Created migrations folder
- [x] Created __init__.py in migrations
- [x] Created migration file with all field additions

### 8. Documentation
- [x] Created PLAYLIST_STREAMING_FEATURE.md
- [x] Created this checklist

---

## 🚀 Next Steps (For Deployment)

### 1. Install Dependencies
```bash
# Install yt-dlp for YouTube video downloading
pip install yt-dlp

# Verify FFmpeg is installed
ffmpeg -version
```

### 2. Run Migrations
```bash
python manage.py migrate streaming
```

### 3. Collect Static Files (if needed)
```bash
python manage.py collectstatic --noinput
```

### 4. Test the Feature
- [ ] Create a stream with media files (existing feature)
- [ ] Create a stream with a YouTube playlist
- [ ] Try shuffling a playlist
- [ ] Verify playlist videos are downloaded correctly
- [ ] Start streaming and monitor logs

### 5. Optional: Update Admin Interface
Consider updating `admin.py` to show new fields:
```python
# Add to StreamAdmin
list_display = [..., 'stream_source', 'playlist_title']
list_filter = [..., 'stream_source']
```

---

## 📋 File Modifications Summary

| File | Type | Changes |
|------|------|---------|
| `apps/streaming/models.py` | Modified | Added 4 new fields to Stream model |
| `apps/streaming/stream_manager.py` | Modified | Added 7 new methods for playlist handling |
| `apps/streaming/views.py` | Modified | Updated stream_create, added get_playlists_api |
| `apps/streaming/urls.py` | Modified | Added 1 new URL pattern |
| `templates/streaming/stream_create.html` | Modified | Major UI updates with source selection |
| `templates/streaming/stream_detail.html` | Modified | Added conditional playlist info section |
| `apps/streaming/migrations/0001_add_playlist_streaming_fields.py` | Created | New migration file |
| `PLAYLIST_STREAMING_FEATURE.md` | Created | Comprehensive documentation |

---

## 🔍 Code Quality Checks

- [x] No syntax errors in Python files
- [x] All imports added
- [x] Logger properly initialized
- [x] Form validation logic implemented
- [x] API error handling included
- [x] Template variables properly passed

---

## 🎯 Feature Highlights

### User Experience
- **Intuitive Source Selection**: Clear radio button choice between media files and playlists
- **Visual Playlist Grid**: Browse playlists with thumbnails and video counts
- **Shuffle Support**: Option to randomize playlist order
- **Stream Details**: Clear indication of stream source and settings

### Technical Implementation
- **Parallel Media Downloads**: Media files downloaded concurrently
- **Sequential Video Downloads**: Playlist videos downloaded sequentially to avoid rate limits
- **Automatic Cleanup**: Temporary files cleaned up after streaming
- **Robust Error Handling**: Comprehensive error messages and logging

---

## ⚠️ Important Notes

1. **yt-dlp Requirement**: Must be installed for playlist functionality
2. **Storage Space**: Ensure `/var/tmp/streams/` has sufficient space
3. **Internet Bandwidth**: Required for downloading YouTube videos
4. **YouTube API Rate Limits**: Limited to 100 playlists per account
5. **Public Playlists**: Videos must be publicly accessible or user must have access

---

## 🆘 Troubleshooting

### If yt-dlp not found:
```bash
pip install --upgrade yt-dlp
# or
apt-get install yt-dlp
```

### If playlist videos not downloading:
- Check internet connection
- Verify videos are publicly accessible on YouTube
- Check `/var/tmp/streams/` has write permissions
- Monitor stream logs for specific errors

### If migrations fail:
```bash
python manage.py makemigrations streaming
python manage.py migrate streaming
```

---

## 📞 Support Resources

- **Documentation**: See `PLAYLIST_STREAMING_FEATURE.md`
- **Stream Logs**: Available on stream detail page
- **System Logs**: Check Django/FFmpeg logs
- **YouTube API Docs**: https://developers.google.com/youtube/v3
- **yt-dlp Docs**: https://github.com/yt-dlp/yt-dlp
