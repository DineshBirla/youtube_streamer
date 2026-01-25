# Playlist Streaming Feature - Installation & Setup Guide

## 📋 Prerequisites

- Python 3.8+
- Django 3.2+
- FFmpeg installed on system
- YouTube OAuth credentials configured
- Active database

---

## 🚀 Installation Steps

### Step 1: Install Required Python Packages

```bash
# Install yt-dlp (required for playlist video downloads)
pip install yt-dlp

# Verify installation
yt-dlp --version
```

### Step 2: Install/Verify System Dependencies

#### On Ubuntu/Debian:
```bash
# Install FFmpeg if not already installed
sudo apt-get update
sudo apt-get install ffmpeg

# Verify FFmpeg installation
ffmpeg -version
```

#### On macOS:
```bash
# Install via Homebrew
brew install ffmpeg yt-dlp

# Verify
ffmpeg -version
yt-dlp --version
```

#### On Windows:
```bash
# Using Chocolatey
choco install ffmpeg yt-dlp

# OR download manually from:
# FFmpeg: https://ffmpeg.org/download.html
# yt-dlp: https://github.com/yt-dlp/yt-dlp/releases
```

### Step 3: Create Required Directories

```bash
# Create temporary streaming directory
mkdir -p /var/tmp/streams
chmod 777 /var/tmp/streams

# On Windows, use:
mkdir C:\temp\streams
```

### Step 4: Run Database Migrations

```bash
# Navigate to project root
cd /workspaces/youtube_streamer

# Run migration to add new database fields
python manage.py migrate streaming

# You should see:
# Running migrations:
#   Applying streaming.0001_add_playlist_streaming_fields...OK
```

### Step 5: Verify Installation

```bash
# Test that all components are importable
python manage.py shell

# In the Django shell, test:
>>> from apps.streaming.stream_manager import StreamManager
>>> from apps.streaming.models import Stream
>>> import yt_dlp
>>> print("All imports successful!")
>>> exit()
```

---

## ✅ Post-Installation Verification

### Test 1: Check YouTube OAuth Configuration
```bash
python manage.py shell

# Verify settings
>>> from django.conf import settings
>>> print(settings.GOOGLE_CLIENT_ID)
>>> print(settings.GOOGLE_CLIENT_SECRET)
>>> # Should print your OAuth credentials
>>> exit()
```

### Test 2: Create Test Stream Data
```bash
python manage.py shell

>>> from django.contrib.auth.models import User
>>> from apps.accounts.models import YouTubeAccount
>>> from apps.streaming.models import Stream

>>> # Check if you have a connected YouTube account
>>> accounts = YouTubeAccount.objects.filter(is_active=True)
>>> print(f"Active YouTube accounts: {accounts.count()}")
>>> 
>>> # If you don't have any, you need to connect one first
>>> exit()
```

### Test 3: Verify File Permissions
```bash
# Test write permissions to temp directory
python manage.py shell

>>> import os
>>> test_dir = "/var/tmp/streams"
>>> test_file = os.path.join(test_dir, "test.txt")
>>> try:
...     with open(test_file, 'w') as f:
...         f.write("test")
...     os.remove(test_file)
...     print("✓ Write permissions OK")
... except Exception as e:
...     print(f"✗ Permission error: {e}")
>>> exit()
```

---

## 🔧 Configuration Options

### Optional: Customize Settings

Edit `config/settings.py` to add:

```python
# Streaming configuration
STREAM_TEMP_DIR = '/var/tmp/streams'  # Temporary files location
MAX_CONCURRENT_DOWNLOADS = 3           # For media files
STREAM_BUFFER_SIZE = '50M'            # FFmpeg buffer size
MAX_STREAM_RESTARTS = 5               # Auto-restart attempts

# YouTube playlist download settings
YT_DLP_FORMAT = 'best[height<=720]/best'  # Video quality
YT_DLP_AUDIO_FORMAT = 'bestaudio'         # Audio format
MAX_PLAYLIST_VIDEOS = 100                  # Max videos per playlist
PLAYLIST_DOWNLOAD_TIMEOUT = 300           # Seconds per video
```

---

## 🌐 Environment Variables (Optional)

Create a `.env` file or add to your environment:

```bash
# YouTube OAuth
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/streaming/oauth2callback/

# Storage
STREAM_TEMP_DIR=/var/tmp/streams
STREAM_LOG_FILE=/var/log/youtube_streamer.log

# Features
ENABLE_PLAYLIST_STREAMING=true
MAX_PLAYLIST_SIZE=100
```

---

## 🧪 Testing the Feature

### Test 1: Create a Playlist Stream (UI Test)

1. Start the development server:
   ```bash
   python manage.py runserver
   ```

2. Login to your application

3. Go to Create Stream page

4. Select "YouTube Playlist" as source

5. If no YouTube account connected:
   - Click "Connect YouTube Account"
   - Complete OAuth flow
   - You'll be redirected back

6. You should see "Playlist not loading" message:
   - This is normal - need to select YouTube account first

7. Select YouTube account from dropdown

8. Wait for playlist grid to load (5-10 seconds)

9. Select a playlist

10. Set stream title and other options

11. Click "Create Stream"

12. You should see stream created successfully

### Test 2: Start Stream (Backend Test)

```bash
python manage.py shell

>>> from apps.streaming.models import Stream
>>> from apps.streaming.stream_manager import StreamManager
>>> 
>>> # Get a playlist stream
>>> stream = Stream.objects.filter(stream_source='playlist').first()
>>> if stream:
...     manager = StreamManager(stream)
...     pid = manager.start_ffmpeg_stream()
...     print(f"Stream started with PID: {pid}")
... else:
...     print("No playlist stream found")
>>> exit()
```

### Test 3: Check Temporary Files

```bash
# During streaming, check downloaded videos
ls -lah /var/tmp/streams/

# View specific stream's files
# {stream_id} is the UUID of the stream
ls -lah /var/tmp/streams/{stream_id}/

# Monitor download progress
watch -n 1 'du -sh /var/tmp/streams/'
```

### Test 4: Check Stream Logs

View logs from:
1. Django shell
2. Stream detail page in UI
3. FFmpeg output in console/log file

---

## 🔍 Troubleshooting

### Issue: "yt-dlp not found"

```bash
# Solution 1: Install via pip
pip install yt-dlp

# Solution 2: Install via system package
sudo apt-get install yt-dlp

# Solution 3: Add to PATH if custom installation
export PATH="/path/to/yt-dlp:$PATH"

# Verify
yt-dlp --version
```

### Issue: "FFmpeg not found"

```bash
# Solution: Install FFmpeg
# Ubuntu/Debian
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg

# Verify
ffmpeg -version
```

### Issue: "Permission denied" for /var/tmp/streams

```bash
# Solution: Fix directory permissions
sudo mkdir -p /var/tmp/streams
sudo chmod 777 /var/tmp/streams

# Or if running under specific user
sudo chown username:username /var/tmp/streams
sudo chmod 755 /var/tmp/streams
```

### Issue: Playlists not loading via API

```bash
# Check:
1. YouTube account is properly connected
2. Account has valid access token
3. Internet connection is working
4. YouTube API is accessible

# Debug in shell:
python manage.py shell
>>> from apps.accounts.models import YouTubeAccount
>>> account = YouTubeAccount.objects.first()
>>> print(f"Token expired: {account.is_token_expired()}")
>>> # If expired, need to reconnect account
>>> exit()
```

### Issue: Videos not downloading from playlist

```bash
# Check:
1. yt-dlp is installed: yt-dlp --version
2. Internet connection is working
3. Playlist videos are public/accessible
4. Disk space available: df -h /var/tmp/

# Test yt-dlp directly:
yt-dlp "https://www.youtube.com/watch?v=VIDEO_ID"
```

### Issue: FFmpeg process crashes

```bash
# Check:
1. FFmpeg version: ffmpeg -version
2. System resources: free -h
3. Disk space: df -h /var/tmp/

# Monitor process:
ps aux | grep ffmpeg

# Check logs for specific errors
cat /var/log/youtube_streamer.log | grep -i error
```

---

## 📊 Health Check Command

Run this script to verify everything is working:

```bash
#!/bin/bash
echo "=== YouTube Streamer Health Check ==="

echo -n "FFmpeg: "
ffmpeg -version > /dev/null 2>&1 && echo "✓" || echo "✗"

echo -n "yt-dlp: "
yt-dlp --version > /dev/null 2>&1 && echo "✓" || echo "✗"

echo -n "Directory writable: "
touch /var/tmp/streams/test.txt > /dev/null 2>&1 && rm /var/tmp/streams/test.txt && echo "✓" || echo "✗"

echo -n "Django migrations: "
python manage.py showmigrations streaming | grep -q "X 0001_add_playlist_streaming_fields" && echo "Applied ✓" || echo "Not applied ✗"

echo -n "Python imports: "
python -c "from apps.streaming.stream_manager import StreamManager; import yt_dlp; print('✓')" 2>/dev/null || echo "✗"

echo "=== Health Check Complete ==="
```

---

## 🚀 Deployment Checklist

Before deploying to production:

- [ ] FFmpeg installed on server
- [ ] yt-dlp installed via pip
- [ ] `/var/tmp/streams/` directory created and writable
- [ ] Migrations applied: `python manage.py migrate`
- [ ] YouTube OAuth credentials configured
- [ ] Static files collected: `python manage.py collectstatic`
- [ ] Tested with at least one playlist stream
- [ ] Error logging configured
- [ ] Disk space monitoring in place (~/20GB recommended)
- [ ] Celery/Background tasks configured (if using)

---

## 📝 Deployment Example (Ubuntu/Nginx)

```bash
# SSH into server
ssh user@your-server.com

# Clone/pull latest code
cd /path/to/youtube_streamer
git pull origin main

# Install/update dependencies
pip install -r requirements.txt
pip install yt-dlp

# Create temp directory
sudo mkdir -p /var/tmp/streams
sudo chmod 777 /var/tmp/streams

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Restart application
systemctl restart gunicorn
systemctl restart nginx

# Verify
curl http://your-server.com/streaming/streams/

# Check logs
tail -f /var/log/gunicorn.log
```

---

## 🔒 Security Checklist

- [ ] HTTPS enabled (required for OAuth)
- [ ] CSRF tokens working
- [ ] Temporary files directory not world-readable
- [ ] FFmpeg running with minimal privileges
- [ ] No sensitive data in logs
- [ ] Rate limiting enabled on API endpoints
- [ ] YouTube OAuth scopes minimized

---

## 📞 Support & Resources

### Documentation Files
- `PLAYLIST_STREAMING_FEATURE.md` - Complete feature documentation
- `DEVELOPER_REFERENCE.md` - Developer quick reference
- `IMPLEMENTATION_CHECKLIST.md` - Implementation checklist

### External Resources
- [yt-dlp Documentation](https://github.com/yt-dlp/yt-dlp)
- [FFmpeg Documentation](https://ffmpeg.org/documentation.html)
- [Django Documentation](https://docs.djangoproject.com/)
- [YouTube API Reference](https://developers.google.com/youtube/v3)

### Debugging
- Check stream logs in UI
- Check Django logs: `tail -f logs/django.log`
- Check FFmpeg output: Monitor stream detail page
- Enable DEBUG mode in settings for verbose output

---

## ✨ Success Indicators

You'll know the feature is working when:

✅ Playlist grid loads when creating a stream
✅ Can select playlists from connected YouTube account
✅ Stream creates successfully with playlist
✅ Videos download to `/var/tmp/streams/`
✅ FFmpeg starts and stream goes live
✅ Stream detail shows playlist information
✅ Logs show video downloads and FFmpeg startup
✅ Shuffle works (videos in different order)
✅ Temp files cleanup after stream stops

---

## 🎉 You're All Set!

Your YouTube Streamer now supports streaming from playlists!

Next steps:
1. Connect your YouTube account
2. Create a playlist stream
3. Start streaming and enjoy!

For support or issues, check the documentation or logs.
