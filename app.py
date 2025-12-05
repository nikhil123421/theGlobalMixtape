import time
import re
import requests
import os
import redis
import json
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# --- CONFIGURATION ---
# Connect to Render's Redis (or local for testing)
redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
r = redis.from_url(redis_url)

# --- STATE MANAGEMENT ---
def get_room_state():
    """Fetch the current state from Redis."""
    raw = r.get("radio_state")
    if raw:
        return json.loads(raw)
    # Default state if Redis is empty
    return {
        "playlist": [],
        "current_track": None,
        "start_time": 0
    }

def save_room_state(state):
    """Save the new state to Redis."""
    r.set("radio_state", json.dumps(state))

# --- HELPER: YOUTUBE METADATA ---
def get_video_details(url):
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

    try:
        # Use oEmbed to get title/thumbnail without an API key
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        resp = requests.get(oembed_url, timeout=3)
        if resp.status_code != 200:
            return None
            
        data = resp.json()
        return {
            "id": video_id,
            "title": data.get("title", "Unknown Track"),
            "thumbnail": data.get("thumbnail_url", ""),
            "duration": 240 # Default fallback duration
        }
    except:
        return None

# --- CACHING VARIABLES ---
# To prevent hammering Redis if 1000 users hit /sync simultaneously
cache_data = None
cache_time = 0

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/add', methods=['POST'])
def add_song():
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({"status": "error", "message": "No URL provided"}), 400

    details = get_video_details(url)
    if details:
        state = get_room_state()
        
        # If nothing is playing, play this immediately
        if state['current_track'] is None:
            state['current_track'] = details
            state['start_time'] = time.time()
        else:
            # Add to queue
            state['playlist'].append(details)
        
        save_room_state(state)
        return jsonify({"status": "success", "track": details})
    
    return jsonify({"status": "error", "message": "Invalid YouTube URL"}), 400

@app.route('/api/sync')
def sync():
    global cache_data, cache_time
    
    # 1. High-Traffic Cache Check
    # If we calculated state less than 1 second ago, return cached version.
    if time.time() - cache_time < 1 and cache_data:
        # Update server_time so clients can calculate offset accurately
        response = cache_data.copy()
        response['server_time'] = time.time()
        return jsonify(response)

    # 2. Fetch Real State
    state = get_room_state()
    
    response = {
        "current_track": state['current_track'],
        "start_time": state['start_time'],
        "server_time": time.time(),
        "queue": state['playlist']
    }

    # 3. Update Cache
    cache_data = response
    cache_time = time.time()

    return jsonify(response)

@app.route('/api/next', methods=['POST'])
def next_track():
    """
    Called when a song ends.
    Includes logic to prevent 'double skipping' if multiple users report end.
    """
    data = request.json
    # The client tells us which song ended for them
    ended_id = data.get('ended_track_id') 

    state = get_room_state()
    current = state['current_track']

    # CRITICAL CHECK:
    # Only skip if the song the user says ended is ACTUALLY the one currently playing.
    # This prevents 1000 users from skipping 1000 songs instantly.
    if current and current['id'] == ended_id:
        if state['playlist']:
            state['current_track'] = state['playlist'].pop(0)
            state['start_time'] = time.time()
        else:
            state['current_track'] = None
            state['start_time'] = 0
        
        save_room_state(state)
        return jsonify({"status": "skipped"})
    
    return jsonify({"status": "already_skipped"})

if __name__ == '__main__':
    # Local development
    app.run(debug=True, port=5000)