# Template Updates for Direct Stream Feature

## Overview
This guide shows how to update your streaming templates to support the new **Direct Stream** playlist mode.

---

## Update: stream_create.html Template

### Add Serve Mode Selection (in Playlist Section)

**Location:** After playlist selection in the form

**HTML Addition:**
```html
<!-- Playlist Serve Mode Selection - NEW -->
<div id="playlist-serve-mode-section" style="display: none;">
    <h4>Streaming Mode</h4>
    <p>Choose how to stream the playlist:</p>
    
    <div class="form-group">
        <label>
            <input type="radio" name="playlist_serve_mode" value="download" checked>
            <strong>Download Videos</strong>
            <p class="small text-muted">
                Videos are downloaded to disk first, then streamed.
                <br>✓ Suitable for: Smaller playlists, 24/7 continuous streaming
                <br>✗ Requires: Disk storage space
            </p>
        </label>
    </div>
    
    <div class="form-group">
        <label>
            <input type="radio" name="playlist_serve_mode" value="direct">
            <strong>Direct Stream (No Download)</strong>
            <p class="small text-muted">
                Videos are streamed directly from YouTube.
                <br>✓ Suitable for: Large playlists, no storage requirement
                <br>✗ Requires: Stable internet connection
            </p>
        </label>
    </div>
</div>
```

### JavaScript to Toggle Section

Add to `stream_create.html` template:

```javascript
<script>
document.addEventListener('DOMContentLoaded', function() {
    const streamSourceRadios = document.querySelectorAll('input[name="stream_source"]');
    const playlistServeModeSection = document.getElementById('playlist-serve-mode-section');
    
    function togglePlaylistSection() {
        const selectedSource = document.querySelector('input[name="stream_source"]:checked').value;
        if (playlistServeModeSection) {
            playlistServeModeSection.style.display = selectedSource === 'playlist' ? 'block' : 'none';
        }
    }
    
    streamSourceRadios.forEach(radio => {
        radio.addEventListener('change', togglePlaylistSection);
    });
    
    // Initial state
    togglePlaylistSection();
});
</script>
```

---

## Complete Form Section Example

Here's a complete example of the playlist form section with direct stream support:

```html
<!-- Stream Source Selection -->
<div class="form-group">
    <label for="stream-source">Stream Source *</label>
    <select id="stream-source" name="stream_source" class="form-control" required>
        <option value="">-- Select Source --</option>
        <option value="media_files">Uploaded Media Files</option>
        <option value="playlist">YouTube Playlist</option>
    </select>
</div>

<!-- Media Files Section (for media_files source) -->
<div id="media-files-section" style="display: none;">
    <div class="form-group">
        <label>Select Media Files *</label>
        <div class="media-files-list">
            {% for media in media_files %}
            <div class="form-check">
                <input type="checkbox" name="media_files" value="{{ media.id }}" 
                       class="form-check-input" id="media-{{ media.id }}">
                <label class="form-check-label" for="media-{{ media.id }}">
                    {{ media.title }} 
                    <small class="text-muted">({{ media.duration|floatformat:0 }}s)</small>
                </label>
            </div>
            {% endfor %}
        </div>
    </div>
</div>

<!-- Playlist Section (for playlist source) -->
<div id="playlist-section" style="display: none;">
    
    <!-- YouTube Account Selection -->
    <div class="form-group">
        <label for="youtube-account">YouTube Account *</label>
        <select id="youtube-account" name="youtube_account" class="form-control" required>
            <option value="">-- Select Account --</option>
            {% for account in youtube_accounts %}
            <option value="{{ account.id }}">{{ account.channel_name }}</option>
            {% endfor %}
        </select>
    </div>

    <!-- Playlist Selection -->
    <div class="form-group">
        <label for="playlist-id">Playlist *</label>
        <select id="playlist-id" name="playlist_id" class="form-control" required>
            <option value="">-- Select Playlist --</option>
        </select>
        <small class="form-text text-muted">Loading playlists...</small>
    </div>

    <!-- Playlist Options -->
    <div class="form-group">
        <div class="form-check">
            <input type="checkbox" name="shuffle_playlist" class="form-check-input" 
                   id="shuffle-playlist">
            <label class="form-check-label" for="shuffle-playlist">
                Shuffle Videos
            </label>
        </div>
    </div>

    <!-- STREAMING MODE SELECTION - NEW -->
    <div id="playlist-serve-mode-section">
        <div class="form-group">
            <label><strong>Streaming Mode</strong></label>
            <p class="text-muted small">Choose how to stream the playlist:</p>
            
            <div class="form-check">
                <input type="radio" name="playlist_serve_mode" value="download" 
                       class="form-check-input" id="mode-download" checked>
                <label class="form-check-label" for="mode-download">
                    <strong>Download Videos</strong>
                    <div class="small text-muted">
                        Videos are downloaded to disk, then streamed continuously.
                        <br>💾 Uses disk storage | ⏱️ Slower startup (5-10 min) | ✅ Good for 24/7 streaming
                    </div>
                </label>
            </div>

            <div class="form-check mt-3">
                <input type="radio" name="playlist_serve_mode" value="direct" 
                       class="form-check-input" id="mode-direct">
                <label class="form-check-label" for="mode-direct">
                    <strong>Direct Stream (No Download) - NEW!</strong>
                    <div class="small text-muted">
                        Videos stream directly from YouTube. No disk storage needed.
                        <br>⚡ Fast startup (30 sec) | 💨 Zero storage | 🔗 Requires stable internet
                    </div>
                </label>
            </div>
        </div>
    </div>

</div>

<!-- Common Options -->
<div class="form-group">
    <div class="form-check">
        <input type="checkbox" name="loop_enabled" class="form-check-input" 
               id="loop-enabled" checked>
        <label class="form-check-label" for="loop-enabled">
            Loop Stream (repeat content continuously)
        </label>
    </div>
</div>

<!-- Toggle JavaScript -->
<script>
document.addEventListener('DOMContentLoaded', function() {
    const streamSourceSelect = document.getElementById('stream-source');
    const mediaFilesSection = document.getElementById('media-files-section');
    const playlistSection = document.getElementById('playlist-section');
    const youtubeAccountSelect = document.getElementById('youtube-account');
    const playlistIdSelect = document.getElementById('playlist-id');
    
    // Toggle sections based on stream source
    streamSourceSelect.addEventListener('change', function() {
        const source = this.value;
        mediaFilesSection.style.display = source === 'media_files' ? 'block' : 'none';
        playlistSection.style.display = source === 'playlist' ? 'block' : 'none';
    });
    
    // Load playlists when YouTube account changes
    youtubeAccountSelect.addEventListener('change', function() {
        const accountId = this.value;
        if (!accountId) {
            playlistIdSelect.innerHTML = '<option value="">-- Select Playlist --</option>';
            return;
        }
        
        // Fetch playlists via API
        fetch(`/streaming/api/playlists/?youtube_account_id=${accountId}`)
            .then(response => response.json())
            .then(data => {
                playlistIdSelect.innerHTML = '<option value="">-- Select Playlist --</option>';
                if (data.status === 'success') {
                    data.playlists.forEach(playlist => {
                        const option = document.createElement('option');
                        option.value = playlist.id;
                        option.textContent = `${playlist.title} (${playlist.item_count} videos)`;
                        playlistIdSelect.appendChild(option);
                    });
                }
            })
            .catch(error => {
                console.error('Error loading playlists:', error);
                playlistIdSelect.innerHTML = '<option value="">Error loading playlists</option>';
            });
    });
});
</script>
```

---

## stream_detail.html Updates

### Display Streaming Mode Information

Add this to show the streaming mode in stream details:

```html
<!-- In stream details section -->
{% if stream.stream_source == 'playlist' %}
<div class="card mb-3">
    <div class="card-body">
        <h5 class="card-title">Playlist Configuration</h5>
        
        <p>
            <strong>Playlist:</strong> {{ stream.playlist_title }}
            <code class="text-muted">{{ stream.playlist_id }}</code>
        </p>
        
        <p>
            <strong>Streaming Mode:</strong>
            {% if stream.playlist_serve_mode == 'direct' %}
                <span class="badge badge-info">⚡ Direct Stream (No Download)</span>
                <small class="text-muted d-block">
                    Videos are streamed directly from YouTube without local storage.
                </small>
            {% else %}
                <span class="badge badge-warning">💾 Download Mode</span>
                <small class="text-muted d-block">
                    Videos are downloaded to disk before streaming.
                </small>
            {% endif %}
        </p>
        
        <p>
            <strong>Shuffle:</strong> 
            {% if stream.shuffle_playlist %}
                <span class="badge badge-success">Enabled</span>
            {% else %}
                <span class="badge badge-secondary">Disabled</span>
            {% endif %}
        </p>
    </div>
</div>
{% endif %}
```

---

## Context Data Provided

The stream_create view now provides the following context:

```python
context = {
    'youtube_accounts': [...],
    'media_files': [...],
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

## CSS Styling Suggestions

Add to your `style.css` for better visual presentation:

```css
/* Direct Stream Feature Styling */

.playlist-serve-mode-option {
    padding: 15px;
    margin: 10px 0;
    border: 1px solid #dee2e6;
    border-radius: 5px;
    cursor: pointer;
    transition: all 0.3s ease;
}

.playlist-serve-mode-option:hover {
    background-color: #f8f9fa;
    border-color: #007bff;
}

.playlist-serve-mode-option input[type="radio"]:checked ~ label {
    font-weight: bold;
    color: #007bff;
}

.streaming-mode-badge {
    display: inline-block;
    padding: 5px 10px;
    border-radius: 20px;
    font-size: 0.85rem;
    font-weight: 500;
}

.streaming-mode-badge.direct {
    background-color: #e7f3ff;
    color: #0066cc;
}

.streaming-mode-badge.download {
    background-color: #fff8e7;
    color: #cc8800;
}
```

---

## Backward Compatibility

✅ **Fully backward compatible** - Existing playlists default to download mode
- Old streams continue using download mode
- New streams can choose either mode
- Templates will work with or without updates
- JavaScript gracefully handles missing elements

---

## Summary

By implementing these template updates, you'll provide users with:

1. ✅ Clear streaming mode selection for playlists
2. ✅ Helpful descriptions of each mode
3. ✅ Visual feedback on selection
4. ✅ Stream details showing active mode
5. ✅ Better user experience overall

The direct stream mode is now fully integrated into your UI! 🎬
