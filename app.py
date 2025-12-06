# --- MUST BE THE VERY FIRST LINES ---
import eventlet
eventlet.monkey_patch()

import time
import re
import requests
import os
import redis
import json
from eventlet import tpool # <--- NEW IMPORT
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_key_for_session'

# --- REDIS SETUP ---
try:
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    r = redis.from_url(redis_url)
    r.ping()
    print("✅ CONNECTED TO REDIS")
except Exception as e:
    print(f"⚠️ REDIS NOT FOUND. Using Mock. Error: {e}")
    class MockRedis:
        def __init__(self): self.store = {}
        def get(self, name): return self.store.get(name)
        def set(self, name, value): self.store[name] = value
    r = MockRedis()

# --- WEBSOCKET SETUP ---
# Added logger=True to help debug if it fails again
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', logger=True, engineio_logger=True)

# --- STATE MANAGEMENT ---
def get_room_state():
    """Fetch the current state from Redis."""
    raw = r.get("radio_state")
    if raw:
        return json.loads(raw)
    return {
        "playlist": [],
        "current_track": None,
        "start_time": 0
    }

def save_room_state(state):
    """Save the new state to Redis."""
    r.set("radio_state", json.dumps(state))

def get_video_details(url):
    """Helper to fetch YouTube metadata."""
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
        # Use oEmbed for metadata
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        
        # --- THE FIX IS HERE ---
        # We use tpool.execute to run requests.get in a background thread.
        # This prevents the main server loop from freezing while waiting for YouTube.
        resp = tpool.execute(requests.get, oembed_url, timeout=3)
        
        if resp.status_code != 200:
            return None
            
        data = resp.json()
        return {
            "id": video_id,
            "title": data.get("title", "Unknown Track"),
            "thumbnail": data.get("thumbnail_url", ""),
            "duration": 240
        }
    except:
        return None

# --- WEBSOCKET EVENTS ---

@socketio.on('connect')
def handle_connect():
    state = get_room_state()
    state['server_time'] = time.time()
    emit('sync_event', state)

def broadcast_update():
    state = get_room_state()
    state['server_time'] = time.time()
    socketio.emit('sync_event', state)

# --- HTTP ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/add', methods=['POST'])
def add_song():
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({"status": "error"}), 400

    details = get_video_details(url)
    if details:
        state = get_room_state()
        
        if state['current_track'] is None:
            state['current_track'] = details
            state['start_time'] = time.time()
        else:
            state['playlist'].append(details)
        
        save_room_state(state)
        
        # TRIGGER REAL-TIME UPDATE
        broadcast_update()
        
        return jsonify({"status": "success", "track": details})
    
    return jsonify({"status": "error", "message": "Invalid YouTube URL"}), 400

@app.route('/api/next', methods=['POST'])
def next_track():
    data = request.json
    ended_id = data.get('ended_track_id') 

    state = get_room_state()
    current = state['current_track']

    if current and current['id'] == ended_id:
        if state['playlist']:
            state['current_track'] = state['playlist'].pop(0)
            state['start_time'] = time.time()
        else:
            state['current_track'] = None
            state['start_time'] = 0
        
        save_room_state(state)
        broadcast_update()
        return jsonify({"status": "skipped"})
    
    return jsonify({"status": "no_skip_needed"})

if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000)
