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
    // If video ends (State=0) and we know what was playing
    if (event.data === 0 && currentVideoId) {
        // We still use HTTP POST to tell the server "I finished"
        // The server will then verify and Broadcast the "Next Song" command back to us via Socket
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
    // (Make sure you added the socket.io script tag in your HTML head!)
    socket = io();

    // LISTEN: This replaces the old 'syncState' polling function
    socket.on('sync_event', (data) => {
        applyServerState(data);
    });
}

// 4. Apply State (The "Puppet Master" Logic)
function applyServerState(data) {
    if (!isStarted || !player) return;

    const { current_track, start_time, server_time, queue } = data;

    updateQueue(queue);

    // Case A: Nothing playing
    if (!current_track) {
        document.getElementById('trackTitle').innerText = "Waiting for songs...";
        if (player.getPlayerState && player.getPlayerState() === 1) {
            player.stopVideo();
        }
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
    // Case C: Same Song (Sync Check)
    else {
        if (player.getCurrentTime) {
            const localTime = player.getCurrentTime();
            
            // With WebSockets, we can be tighter (2 seconds) because updates are instant
            if (Math.abs(localTime - elapsed) > 2) {
                player.seekTo(elapsed, true);
            }

            if (player.getPlayerState() !== 1 && player.getPlayerState() !== 3) {
                player.playVideo();
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

    // We send the song via HTTP POST (Reliable)
    // The server will process it and send the 'sync_event' via WebSocket to update the UI
    try {
        await fetch('/api/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        });
        
        input.value = ''; 
        // No need to call syncState() manually anymore! The socket will do it.
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
    queue.forEach(track => {
        const li = document.createElement('li');
        li.innerText = track.title;
        list.appendChild(li);
    });
}