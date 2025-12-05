let player;
let isStarted = false;
let currentVideoId = null;
let syncInterval;

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
    // If video ends (State=0)
    if (event.data === 0) {
        // Tell the server specifically WHICH video ended
        // This prevents the "Race Condition" where the playlist skips 
        // multiple times if multiple users report the end at once.
        if (currentVideoId) {
            fetch('/api/next', { 
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ended_track_id: currentVideoId })
            });
        }
    }
}

// 3. Start App Logic
function startApp() {
    document.getElementById('startOverlay').style.display = 'none';
    isStarted = true;
    
    // Initial Sync
    syncState(); 
    
    // SCALE FIX: Poll every 10 seconds (instead of 2)
    // This reduces server load by 500%
    syncInterval = setInterval(syncState, 10000); 
}

// 4. The Sync Logic
async function syncState() {
    if (!isStarted || !player) return;

    try {
        const res = await fetch('/api/sync');
        const data = await res.json();
        const { current_track, start_time, server_time, queue } = data;

        updateQueue(queue);

        // Case A: Nothing playing
        if (!current_track) {
            document.getElementById('trackTitle').innerText = "Waiting for songs...";
            // If player is running, stop it
            if (player.getPlayerState && player.getPlayerState() === 1) {
                player.stopVideo();
            }
            return;
        }

        document.getElementById('trackTitle').innerText = current_track.title;

        // Calculate where the song should be
        const elapsed = server_time - start_time;

        // Case B: A new song has started
        if (currentVideoId !== current_track.id) {
            currentVideoId = current_track.id;
            player.loadVideoById(currentVideoId, elapsed);
            // Ensure audio is unmuted (browsers sometimes auto-mute hidden videos)
            player.unMute(); 
            player.setVolume(100);
        } 
        // Case C: Same song, check for drift
        else {
            // Only seek if the player exists and is ready
            if (player.getCurrentTime) {
                const localTime = player.getCurrentTime();
                
                // If local player is off by more than 5 seconds, snap it back
                if (Math.abs(localTime - elapsed) > 2) {
                    player.seekTo(elapsed, true);
                }

                // If user paused it or it buffered, force play
                if (player.getPlayerState() !== 1 && player.getPlayerState() !== 3) {
                    player.playVideo();
                }
            }
        }
    } catch (err) {
        console.error("Sync failed:", err);
    }
}

// 5. Add Song
async function addSong() {
    const input = document.getElementById('songUrl');
    const url = input.value;
    if (!url) return;

    // Visual feedback
    input.value = "Adding...";
    input.disabled = true;

    try {
        const res = await fetch('/api/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        });

        const data = await res.json();
        if (data.status === 'success') {
            input.value = ''; // Clear input
            syncState(); // Update UI immediately
        } else {
            alert("Error: " + data.message);
            input.value = '';
        }
    } catch (e) {
        alert("Failed to connect to server");
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