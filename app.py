import time
import re
import requests
import json
import os
from flask import Flask, render_template, request, jsonify
import redis

app = Flask(__name__)

# --- REDIS SETUP ---
# Expect REDIS_URL in environment (Render sets this for managed Redis)
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
r = redis.from_url(REDIS_URL, decode_responses=True)

# Redis keys
KEY_PLAYLIST = "radio:playlist"        # list of JSON-encoded tracks
KEY_CURRENT = "radio:current_track"    # JSON-encoded current track
KEY_START = "radio:track_start_time"   # float (timestamp)
KEY_LAST_NEXT = "radio:last_next"      # float (timestamp of last next request)

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
        data = requests.get(oembed_url, timeout=5).json()
        return {
            "id": video_id,
            "title": data.get("title", "Unknown Track"),
            "thumbnail": data.get("thumbnail_url", ""),
            # We default to 4 minutes if we can't guess duration
            "duration": 240
        }
    except Exception as e:
        return None

# Utility: get current track dict or None
def get_current_track():
    s = r.get(KEY_CURRENT)
    if not s:
        return None
    try:
        return json.loads(s)
    except:
        return None

# Utility: set current track dict (or None to clear)
def set_current_track(track):
    if track is None:
        r.delete(KEY_CURRENT)
    else:
        r.set(KEY_CURRENT, json.dumps(track))

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/add', methods=['POST'])
def add_song():
    data = request.json
    url = data.get('url')
    details = get_video_details(url)

    if not details:
        return jsonify({"status": "error", "message": "Invalid URL"}), 400

    # Use redis to set current track or push to playlist
    current = get_current_track()
    if current is None:
        # start immediately
        set_current_track(details)
        now = time.time()
        r.set(KEY_START, now)
        return jsonify({"status": "success", "track": details})
    else:
        # push to playlist (right push)
        r.rpush(KEY_PLAYLIST, json.dumps(details))
        return jsonify({"status": "success", "track": details})

@app.route('/api/sync')
def sync():
    current = get_current_track()
    start_time = r.get(KEY_START)
    server_time = time.time()

    if start_time:
        try:
            start_time = float(start_time)
        except:
            start_time = 0.0
    else:
        start_time = 0.0

    # Read playlist
    raw_list = r.lrange(KEY_PLAYLIST, 0, -1)  # returns list of JSON strings
    queue = []
    for item in raw_list:
        try:
            queue.append(json.loads(item))
        except:
            pass

    return jsonify({
        "current_track": current,
        "start_time": start_time,
        "server_time": server_time,
        "queue": queue
    })

@app.route('/api/next', methods=['POST'])
def next_track():
    """
    Called by frontend when a song finishes.
    We protect against duplicate 'next' spam by checking last_next timestamp.
    Then atomically pop next from playlist and set as current.
    """
    now = time.time()
    last_next = r.get(KEY_LAST_NEXT)
    if last_next:
        try:
            last_next = float(last_next)
        except:
            last_next = 0.0
    else:
        last_next = 0.0

    # Ignore duplicate next calls within 1 second
    if now - last_next < 1.0:
        return jsonify({"status": "ignored_duplicate"})

    # Set last_next timestamp
    r.set(KEY_LAST_NEXT, now)

    # Atomically pop first playlist item and set current
    # We'll use a pipeline to ensure atomicity-ish
    pipe = r.pipeline()
    pipe.lpop(KEY_PLAYLIST)   # pop left (oldest)
    popped = pipe.execute()[0]

    if popped:
        try:
            next_track = json.loads(popped)
        except:
            next_track = None
    else:
        next_track = None

    if next_track:
        set_current_track(next_track)
        r.set(KEY_START, now)
        return jsonify({"status": "playing next", "track": next_track})
    else:
        # no more tracks
        set_current_track(None)
        r.set(KEY_START, 0)
        return jsonify({"status": "queue empty"})

if __name__ == '__main__':
    # Optional: try connecting to Redis on startup to surface errors early
    try:
        r.ping()
        print("Connected to Redis")
    except Exception as e:
        print("Warning: cannot connect to Redis:", e)
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
