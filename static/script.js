let player;
let isStarted = false;
let currentVideoId = null;

// 1. Initialize YouTube API
function onYouTubeIframeAPIReady() {
    player = new YT.Player('player', {
        height: '1',
        width: '1',
        playerVars: {
            'autoplay': 0,
            'controls': 0
        },
        events: {
            'onStateChange': onPlayerStateChange
        }
    });
}

// 2. Handle Song Ending (Auto-Next)
function onPlayerStateChange(event) {
    if (event.data === YT.PlayerState.ENDED) {
        // tell server to advance to next track
        fetch('/api/next', { method: 'POST' }).catch(console.error);
    }
}

// 3. User Click to Start (Browser Requirement)
function startApp() {
    document.getElementById('startOverlay').style.display = 'none';
    isStarted = true;
    syncState(); // Trigger immediate sync
    setInterval(syncState, 2000); // Poll every 2 seconds
}

// 4. The Brain: Sync with Server
async function syncState() {
    if (!isStarted || !player) return;

    let res;
    try {
        res = await fetch('/api/sync');
    } catch (e) {
        console.error('sync failed', e);
        return;
    }
    let data;
    try {
        data = await res.json();
    } catch (e) {
        console.error('invalid json', e);
        return;
    }

    const { current_track, start_time, server_time, queue } = data;
    const cassette = document.querySelector('.cassette');

    // A. Update UI
    updateQueue(queue);

    if (!current_track) {
        document.getElementById('trackTitle').innerText = "End of Tape (Add a Song)";
        cassette.classList.remove('spinning');
        try { player.stopVideo(); } catch (e) {}
        currentVideoId = null;
        return;
    }

    document.getElementById('trackTitle').innerText = current_track.title;

    // B. Sync Audio
    // Calculate how many seconds have passed since the song started on server
    const elapsed = server_time - start_time;

    // If we are playing a different song than the server, load the new one
    if (currentVideoId !== current_track.id) {
        currentVideoId = current_track.id;
        // load with offset (elapsed)
        try {
            player.loadVideoById(currentVideoId, elapsed);
            cassette.classList.add('spinning');
        } catch (e) {
            console.error('error loading video', e);
        }
    } 
    else {
        // We are on the same song, check if we drifted too far (sync check)
        try {
            const localTime = player.getCurrentTime();
            if (Math.abs(localTime - elapsed) > 3) {
                player.seekTo(elapsed, true);
            }

            // Ensure it's playing (state 1 = playing, 3 = buffering)
            const state = player.getPlayerState();
            if (state !== 1 && state !== 3) {
                player.playVideo();
            }
        } catch (e) {
            // sometimes player isn't ready yet
        }
    }
}

// 5. Add Song Logic
async function addSong() {
    const url = document.getElementById('songUrl').value;
    if (!url) return;

    try {
        const res = await fetch('/api/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        });

        const data = await res.json();
        if (data.status === 'success') {
            document.getElementById('songUrl').value = ''; // Clear input
            syncState();
        } else {
            alert("Invalid YouTube Link!");
        }
    } catch (e) {
        alert("Failed to add song. Try again.");
        console.error(e);
    }
}

// 6. Helper: Render Queue
function updateQueue(queue) {
    const list = document.getElementById('queueList');
    if (!list) return;
    list.innerHTML = '';
    queue.forEach(track => {
        const li = document.createElement('li');
        li.innerText = track.title;
        list.appendChild(li);
    });
}
