let player;
let isStarted = false;
let currentVideoId = null;
let socket; // Stores the WebSocket connection

// 1. Initialize YouTube API
function onYouTubeIframeAPIReady() {
    player = new YT.Player('player', {
        height: '1',
        width: '1',
        playerVars: {
            'autoplay': 0,
            'controls': 0,
            'disablekb': 1,
            'fs': 0
        },
        events: {
            'onStateChange': onPlayerStateChange
        }
    });
}

// 2. Handle Song Ending
function onPlayerStateChange(event) {
    if (event.data === 0 && currentVideoId) {
        fetch('/api/next', { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ended_track_id: currentVideoId })
        });
    }
}

// 3. Start App & Connect Socket
function startApp() {
    document.getElementById('startOverlay').style.display = 'none';
    isStarted = true;
    
    // CONNECT TO WEBSOCKET
    socket = io();

    socket.on('sync_event', (data) => {
        applyServerState(data);
    });
}

// 4. Apply State (FIXED: Now reads 'playlist' correctly)
function applyServerState(data) {
    if (!isStarted || !player) return;

    // FIX: Python sends 'playlist', NOT 'queue'
    const { current_track, start_time, server_time, playlist } = data;
    
    // Safety check: ensure queue is an array even if server sends nothing
    const queue = playlist || [];

    updateQueue(queue);

    // Case A: Nothing playing
    if (!current_track) {
        document.getElementById('trackTitle').innerText = "Waiting for songs...";
        if (player.getPlayerState && player.getPlayerState() === 1) {
            player.stopVideo();
        }
        // STOP SPINNING
        if (leftSpool) leftSpool.classList.remove('spinning');
        if (rightSpool) rightSpool.classList.remove('spinning');
        return;
    }

    document.getElementById('trackTitle').innerText = current_track.title;

    // Calculate elapsed time using server's clock
    const elapsed = server_time - start_time;

    // Case B: New Song
    if (currentVideoId !== current_track.id) {
        currentVideoId = current_track.id;
        player.loadVideoById(currentVideoId, elapsed);
        player.unMute(); 
        player.setVolume(100);
    } 
    else {
        if (player.getCurrentTime) {
            const localTime = player.getCurrentTime();
            if (Math.abs(localTime - elapsed) > 2) {
                player.seekTo(elapsed, true);
            }

            const playerState = player.getPlayerState();
            // If playing (1) or buffering (3), ensure it's playing and spinning
            if (playerState === 1 || playerState === 3) {
                 if (playerState !== 1) player.playVideo();
                 // START SPINNING
                 if (leftSpool) leftSpool.classList.add('spinning');
                 if (rightSpool) rightSpool.classList.add('spinning');
            } 
            // If paused (2) or ended (0), stop spinning
            else if (playerState === 2 || playerState === 0) {
                 // STOP SPINNING
                 if (leftSpool) leftSpool.classList.remove('spinning');
                 if (rightSpool) rightSpool.classList.remove('spinning');
            }
        }
    }
}

// 5. Add Song
async function addSong() {
    const input = document.getElementById('songUrl');
    const url = input.value;
    if (!url) return;

    input.value = "Adding...";
    input.disabled = true;

    try {
        await fetch('/api/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        });
        input.value = ''; 
    } catch (e) {
        alert("Failed to add song.");
    } finally {
        input.disabled = false;
    }
}

// 6. UI Helper
function updateQueue(queue) {
    const list = document.getElementById('queueList');
    if(!list) return;
    
    list.innerHTML = '';
    // Extra safety check to prevent crash
    if (Array.isArray(queue)) {
        queue.forEach(track => {
            const li = document.createElement('li');
            li.innerText = track.title;
            list.appendChild(li);
        });
    }
}
