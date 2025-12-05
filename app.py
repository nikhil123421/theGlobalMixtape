import time
import re
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# --- IN-MEMORY DATABASE ---
# In a real production app, you might use SQLite, 
# but for simplicity, lists work fine while the server is running.
playlist = [] 
current_track = None
track_start_time = 0

# --- HELPER: EXTRACT ID & METADATA ---
def get_video_details(url):
    # 1. Extract ID using Regex
    video_id = None
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            break
    
    if not video_id:
        return None

    # 2. Fetch Metadata using No-Key oEmbed
    try:
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        data = requests.get(oembed_url).json()
        return {
            "id": video_id,
            "title": data.get("title", "Unknown Track"),
            "thumbnail": data.get("thumbnail_url", ""),
            # We default to 4 minutes if we can't guess duration, 
            # as oEmbed doesn't always provide duration.
            # The client logic handles 'song ending' events anyway.
            "duration": 240 
        }
    except:
        return None

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/add', methods=['POST'])
def add_song():
    data = request.json
    url = data.get('url')
    details = get_video_details(url)
    
    if details:
        # Check if playlist is empty and nothing is playing, play immediately
        global current_track, track_start_time
        if current_track is None:
            current_track = details
            track_start_time = time.time()
        else:
            playlist.append(details)
        return jsonify({"status": "success", "track": details})
    return jsonify({"status": "error", "message": "Invalid URL"}), 400

@app.route('/api/sync')
def sync():
    global current_track, track_start_time

    # logic to check if song ended
    if current_track:
        elapsed = time.time() - track_start_time
        # Note: Since we don't have exact duration from oEmbed, 
        # we rely on the frontend to tell us when a song ends, 
        # OR we just let it run. For this simple version, we stick to state.
    
    return jsonify({
        "current_track": current_track,
        "start_time": track_start_time,
        "server_time": time.time(),
        "queue": playlist
    })

@app.route('/api/next', methods=['POST'])
def next_track():
    """Called by frontend when a song finishes"""
    global current_track, track_start_time
    
    if playlist:
        current_track = playlist.pop(0)
        track_start_time = time.time()
    else:
        current_track = None
        track_start_time = 0
    
    return jsonify({"status": "playing next"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)