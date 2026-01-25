# YouTube Streamer - Playlist Streaming Feature Documentation

## Overview
This feature allows users to stream content from two sources:
1. **Uploaded Media Files** - Traditional method: users upload media files and stream them
2. **YouTube Playlists** - New feature: users can select a playlist from their connected YouTube channel, and the system automatically downloads and streams all videos from that playlist

---

## Changes Made

### 1. **Database Models** (`apps/streaming/models.py`)

#### New Fields Added to `Stream` Model:
- **`stream_source`** (CharField)
  - Choices: `'media_files'` or `'playlist'`
  - Default: `'media_files'`
  - Determines whether the stream uses uploaded files or YouTube playlist

- **`playlist_id`** (CharField)
  - Stores the YouTube playlist ID
  - Blank if using media files

- **`playlist_title`** (CharField)
  - Caches the playlist title for display purposes
  - Blank if using media files

- **`shuffle_playlist`** (BooleanField)
  - Default: False
  - When True, videos from playlist are shuffled before streaming

#### Modified Fields:
- **`media_files`** (ManyToManyField)
  - Now has `blank=True` to allow playlist-only streams

---

### 2. **Stream Manager** (`apps/streaming/stream_manager.py`)

#### New Methods Added:

1. **`start_ffmpeg_stream()` (Updated)**
   - Now checks `stream.stream_source` and routes to appropriate method
   - Supports both media files and playlist streams

2. **`_start_media_files_stream()`**
   - Original streaming logic for uploaded media files
   - Downloads files in parallel, creates concat file, starts FFmpeg

3. **`_start_playlist_stream()`**
   - New method for playlist streaming
   - Downloads videos from YouTube playlist and streams them

4. **`_download_playlist_videos()`**
   - Fetches all video IDs from the YouTube playlist
   - Downloads each video using yt-dlp
   - Returns a dictionary of downloaded file paths

5. **`_get_playlist_video_ids()`**
   - Queries YouTube API to get all video IDs in the playlist
   - Supports pagination for large playlists
   - Implements shuffle functionality if enabled
   - Returns list of video IDs

6. **`_download_youtube_video()`**
   - Downloads individual YouTube videos using yt-dlp
   - Supports multiple formats (mp4, mkv, webm, flv)
   - Returns the path to the downloaded file

7. **`_create_playlist_concat_file()`**
   - Creates FFmpeg concat file for downloaded playlist videos
   - Similar to media files concat but uses downloaded videos

---

### 3. **Views** (`apps/streaming/views.py`)

#### Updated `stream_create()` View:
- Now accepts `stream_source` parameter
- Validates based on source type:
  - For media files: requires at least one media file selected
  - For playlist: requires a valid playlist ID selected
- Creates Stream object with new fields
- Added `shuffle_playlist` field handling

#### New API Endpoint: `get_playlists_api()`
```
GET /streaming/api/playlists/?youtube_account_id={id}
```
- Fetches playlists from user's connected YouTube channel
- Returns JSON with playlist list:
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

### 4. **URLs** (`apps/streaming/urls.py`)

#### New URL Pattern:
```python
path('api/playlists/', views.get_playlists_api, name='get_playlists_api'),
```

---

### 5. **Templates**

#### `stream_create.html` (Major Updates)

**New UI Elements:**
- **Stream Source Selector**
  - Radio buttons to choose between "Media Files" and "Playlist"
  - Shows description for each option

- **Content Source Section**
  - Dynamically hides/shows based on selected source
  - For media files: shows existing media selection UI
  - For playlists: shows playlist selector UI

- **Playlist Selection UI**
  - Grid layout showing available playlists
  - Each playlist card displays:
    - Thumbnail image
    - Playlist title
    - Number of videos
  - Radio buttons for selection
  - Styled card indicates selected playlist

- **Shuffle Option**
  - Checkbox to enable/disable playlist shuffling
  - Only visible when playlist is selected

**New JavaScript Functions:**
- `onStreamSourceChange()` - Handles switching between media and playlist modes
- `onYouTubeAccountChange()` - Loads playlists when account is selected
- `loadPlaylists()` - Fetches playlists via API and displays in grid
- `selectPlaylist()` - Handles playlist selection
- `validateFormSubmit()` - Validates form based on selected source

#### `stream_detail.html` (Updates)

**Added Information:**
- **Stream Source Badge**
  - Shows whether stream is from "Media Files" or "Playlist"
  - In the Stream Information table

- **Conditional Display**
  - Media Files section: shown only for media file streams
  - New Playlist Information section: shown only for playlist streams
    - Displays playlist title and ID
    - Shows shuffle status
    - Informational alert about automatic video downloading

---

### 6. **Database Migration**

Created migration file: `apps/streaming/migrations/0001_add_playlist_streaming_fields.py`
- Adds all new fields to Stream model
- Makes media_files field optional (blank=True)
- Sets default values for new fields

---

## How to Use

### For Users:

#### Streaming from Media Files (Existing Feature):
1. Go to "Create Stream"
2. Select "Uploaded Media Files" as content source
3. Select uploaded media files from your library
4. Configure other options (title, description, thumbnail, loop)
5. Create and start stream

#### Streaming from Playlist (New Feature):
1. Go to "Create Stream"
2. Select "YouTube Playlist" as content source
3. Select a YouTube account
4. Playlist grid loads showing available playlists
5. Click on a playlist to select it
6. Optionally enable "Shuffle Playlist"
7. Configure other options (title, description, thumbnail, loop)
8. Create and start stream

### Installation Steps:

1. **Apply Migrations:**
   ```bash
   python manage.py migrate streaming
   ```

2. **Install yt-dlp** (Required for playlist video downloads):
   ```bash
   pip install yt-dlp
   ```
   OR
   ```bash
   apt-get install yt-dlp
   ```

3. **Ensure FFmpeg is installed:**
   ```bash
   apt-get install ffmpeg
   ```

---

## Requirements

### Python Packages:
- `yt-dlp` - For downloading YouTube videos from playlists

### System Packages:
- `ffmpeg` - For video streaming (already required)
- `ffprobe` - For video information (usually included with ffmpeg)

### Environment:
- Valid YouTube OAuth credentials
- Storage space for temporary downloaded videos
- Sufficient bandwidth for streaming

---

## Technical Details

### Video Download Process:
1. Get all video IDs from the selected playlist
2. Download each video using yt-dlp
3. Videos are downloaded to a temporary directory specific to the stream
4. Downloaded videos are converted/re-encoded if needed
5. A concat file is created with all video paths
6. FFmpeg uses the concat file to stream all videos sequentially

### Quality Settings:
- Videos downloaded up to 720p resolution (customizable)
- Best available format within resolution limit
- Audio is re-encoded to AAC for compatibility

### Temporary Files:
- Downloaded videos stored in `/var/tmp/streams/{stream_id}/`
- Files automatically cleaned up when stream stops
- Concat file stored in same directory

---

## Error Handling

### Common Issues:

1. **"yt-dlp not found"**
   - Solution: Install yt-dlp via pip or apt

2. **"No videos in playlist"**
   - Solution: Ensure playlist is public or user has access
   - Check that playlist contains at least one video

3. **"Failed to download video"**
   - Solution: Check internet connection
   - Verify YouTube video is available/public
   - Check disk space in `/var/tmp/streams/`

4. **API Rate Limiting**
   - YouTube API has rate limits
   - Limit playlists returned to 100 (configurable in code)
   - Videos downloaded sequentially to avoid rate limiting

---

## Security Considerations

- Playlist selection validates against user's connected YouTube accounts
- Only playlists from authenticated user's channel are accessible
- Downloaded videos are temporary and deleted after stream stops
- Shuffle option doesn't modify playlist on YouTube, only locally

---

## Performance Notes

- Playlist videos are downloaded sequentially to avoid overwhelming network
- Downloads happen in `/var/tmp/streams/` for fast I/O
- FFmpeg command optimized for RTMP streaming
- Temporary files cleaned up after stream completion

---

## Future Enhancements

Possible improvements:
1. Batch download with progress tracking
2. Quality selection UI for playlist videos
3. Preview thumbnail generation for playlists
4. Playlist caching to avoid repeated downloads
5. Support for custom video order within playlists
6. Support for YouTube channel uploads as source

---

## Support

For issues or questions:
1. Check stream logs in the stream detail page
2. Review system logs for FFmpeg output
3. Verify YouTube API credentials are valid
4. Ensure yt-dlp is installed and updated
