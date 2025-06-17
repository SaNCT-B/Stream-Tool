const express = require('express');
const bodyParser = require('body-parser');
const WebSocket = require('ws');
const { TikTokLiveConnection, WebcastEvent } = require('tiktok-live-connector');
const tmi = require('tmi.js');
const fs = require('fs');
const path = require('path');

const ERROR_LOG = 'error_output.log';
// Overwrite error log at startup
fs.writeFileSync(ERROR_LOG, '', 'utf8');
function logError(err) {
    const msg = `[${new Date().toISOString()}] ${err && err.stack ? err.stack : err}\n`;
    fs.appendFile(ERROR_LOG, msg, () => {});
}

const app = express();
const port = process.argv[2] || 8080;

let currentKeyword = '';
let viewersSet = new Set();
let wsClient = null;
let tiktokConnection = null;
let twitchClient = null;
let retryCounts = { tiktok: 0, twitch: 0 };
const MAX_RETRIES = 3;
let recentViewers = [];

// Clear state on startup
currentKeyword = '';
viewersSet.clear();
recentViewers = [];
console.log('🔄 State cleared on server startup');

app.use(bodyParser.json());
app.use(express.static(__dirname));

// Global error handler
process.on('uncaughtException', logError);
process.on('unhandledRejection', logError);

const server = app.listen(port, () => {
    console.log(`🚀 Server is running on http://localhost:${port}`);
});

const shutdown = () => {
    console.log('🛑 Shutting down server...');
    if (tiktokConnection) tiktokConnection.disconnect();
    if (twitchClient) {
        twitchClient.disconnect();
        twitchClient = null;
    }
    if (wsClient) wsClient.close();
    server.close(() => {
        console.log('✅ HTTP server closed');
        process.exit(0);
    });
};

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

const wss = new WebSocket.Server({ server });

function heartbeat() {
    this.isAlive = true;
}

wss.on('connection', ws => {
    console.log('🔌 GUI connected via WebSocket');
    ws.isAlive = true;
    wsClient = ws;

    ws.on('pong', heartbeat);

    ws.on('close', () => {
        console.log('❌ GUI WebSocket disconnected');
        wsClient = null;
    });

    ws.on('error', error => {
        console.log(`❌ WebSocket error: ${error}`);
    });
});

const interval = setInterval(() => {
    wss.clients.forEach(ws => {
        if (!ws.isAlive) return ws.terminate();
        ws.isAlive = false;
        ws.ping();
    });
}, 30000);

server.on('close', () => clearInterval(interval));

function createKeywordMatcher(keyword) {
    const normalize = t => t.toLowerCase().replace(/['']/g, "'").replace(/\s+/g, ' ').trim();
    const normKeyword = normalize(keyword);
    const emojiRegex = /^[\u{1F300}-\u{1F9FF}]+$/u;
    if (emojiRegex.test(keyword)) return new RegExp(`^${keyword}+$`, 'u');
    const words = normKeyword.split(/\s+/);

    if (words.length > 1) {
        const pattern = words.map(w => w.replace(/'/g, "").replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join("[\\s']*");
        return new RegExp(`^${pattern}[!.?]*(?:[\u{1F300}-\u{1F9FF}]+)?$`, 'iu');
    } else {
        const pattern = words[0].replace(/'/g, "").split('').map(c => `${c}+`).join('');
        return new RegExp(`^${pattern}[!.?]*(?:[\u{1F300}-\u{1F9FF}]+)?$`, 'iu');
    }
}

async function connectTikTok(username, res, responded) {
    if (tiktokConnection) tiktokConnection.disconnect();
    const sendOnce = (code, payload) => {
        if (!responded.sent) {
            responded.sent = true;
            res.status(code).json(payload);
        }
    };

    tiktokConnection = new TikTokLiveConnection(username);

    try {
        await tiktokConnection.connect();
        console.log(`Connected to TikTok user: ${username}`);

        const timeout = setTimeout(() => {
            console.log("❌ No viewer data received, assuming user is not live.");
            tiktokConnection.disconnect();
            sendOnce(400, { success: false, error: "User is not live" });
        }, 5000);

        tiktokConnection.on(WebcastEvent.ROOM_USER, data => {
            const viewerCount = data?.viewerCount ?? 0;
            if (wsClient?.readyState === WebSocket.OPEN) {
                wsClient.send(JSON.stringify({ type: 'viewerCount', platform: 'tiktok', count: viewerCount }));
            }
            clearTimeout(timeout);
            sendOnce(200, { success: true });
        });

        tiktokConnection.once(WebcastEvent.STREAM_END, () => {
            console.log("🔴 Stream ended.");
            clearTimeout(timeout);
            tiktokConnection.disconnect();
            sendOnce(400, { success: false, error: "User is not live" });
        });

        tiktokConnection.on(WebcastEvent.CHAT, data => {
            const nickname = data.user && data.user.nickname ? data.user.nickname : (data.user && data.user.uniqueId ? data.user.uniqueId : 'Unknown');
            const text = data.comment || '';
            console.log(`\x1b[32m[💬]\x1b[0m ${nickname}: \x1b[32m${text}\x1b[0m`);
            if (currentKeyword) {
                const matcher = createKeywordMatcher(currentKeyword);
                if (matcher.test(text) && !viewersSet.has(nickname)) {
    viewersSet.add(nickname);
    addRecentViewer(nickname, 'tiktok');
    // Send to overlay
    wsClient?.readyState === WebSocket.OPEN && wsClient.send(JSON.stringify({
        type: 'chat',
        viewerName: nickname,
        platform: 'tiktok',
        text
    }));
    // Also send to GUI
    wss.clients.forEach(client => {
        if (client.readyState === WebSocket.OPEN) {
            client.send(JSON.stringify({
                type: 'chat',
                viewerName: nickname,
                platform: 'tiktok',
                text
            }));
        }
    });
}
            }
        });
    } catch (err) {
        console.log("❌ Error connecting to TikTok:", err);
        logError(err);
        if (retryCounts.tiktok < MAX_RETRIES) {
            retryCounts.tiktok++;
            const delay = 3000 * retryCounts.tiktok;
            console.log(`🔁 Retrying TikTok (attempt ${retryCounts.tiktok}) in ${delay / 1000}s...`);
            setTimeout(() => connectTikTok(username, res, responded), delay);
        } else {
            sendOnce(503, { success: false, error: "TikTok signing server failed (504). Please try again shortly." });
        }

    }
}

app.post('/start', async (req, res) => {
    const { username, platform } = req.body;
    if (!username || !platform) return res.status(400).json({ success: false, error: "Missing username or platform" });
    const responded = { sent: false };
    retryCounts[platform] = 0;

    if (platform === 'tiktok') return connectTikTok(username, res, responded);

    if (platform === 'twitch') {
        try {
            if (twitchClient) await twitchClient.disconnect();
            twitchClient = new tmi.Client({ channels: [username] });
            twitchClient.on('message', (channel, tags, message, self) => {
                if (self) return;
                const user = tags['display-name'] || tags.username;
                console.log(`\x1b[35m[💬]\x1b[0m ${user}: \x1b[35m${message}\x1b[0m`);
                const matcher = createKeywordMatcher(currentKeyword);
                if (matcher.test(message) && !viewersSet.has(user)) {
    viewersSet.add(user);
    addRecentViewer(user, 'twitch');
    // Send to overlay
    wsClient?.readyState === WebSocket.OPEN && wsClient.send(JSON.stringify({
        type: 'chat',
        viewerName: user,
        platform: 'twitch',
        text: message
    }));
    // Also send to GUI
    wss.clients.forEach(client => {
        if (client.readyState === WebSocket.OPEN) {
            client.send(JSON.stringify({
                type: 'chat',
                viewerName: user,
                platform: 'twitch',
                text: message
            }));
        }
    });
}
            });
            await twitchClient.connect();
            console.log(`Connected to Twitch user: ${username}`);
            res.status(200).json({ success: true });
        } catch (err) {
            console.log("❌ Twitch connection error:", err);
            logError(err);
            if (retryCounts.twitch < MAX_RETRIES) {
                retryCounts.twitch++;
                console.log(`🔁 Retrying Twitch (attempt ${retryCounts.twitch})...`);
                setTimeout(() => app._router.handle(req, res, () => {}), 1000 * retryCounts.twitch);
            } else {
                res.status(500).json({ success: false, error: "Unable to connect to Twitch" });
            }
        }
    }
});

app.post('/keyword', (req, res) => {
    currentKeyword = req.body.keyword?.trim();
    viewersSet.clear();
    recentViewers = [];
    console.log('🔑 Keyword set to:', currentKeyword);
    if (wsClient?.readyState === WebSocket.OPEN) {
        wsClient.send(JSON.stringify({ type: 'control', action: 'clearViewers' }));
    }
    res.json({ success: true });
});

app.post('/clearKeyword', (req, res) => {
    currentKeyword = '';
    viewersSet.clear();
    recentViewers = [];
    console.log('🔑 Keyword cleared');
    if (wsClient?.readyState === WebSocket.OPEN) {
        wsClient.send('clearViewers');
    }
    res.send('Keyword cleared');
});

app.post('/disconnect', async (req, res) => {
    const platform = req.body?.platform;
    if (platform === 'all') {
        if (tiktokConnection) await tiktokConnection.disconnect();
        if (twitchClient) await twitchClient.disconnect();
        wsClient?.readyState === WebSocket.OPEN && wsClient.send(JSON.stringify({ type: 'control', action: 'clearViewers' }));
        currentKeyword = '';
        viewersSet.clear();
        recentViewers = [];
    } else if (platform === 'tiktok' && tiktokConnection) {
        await tiktokConnection.disconnect();
        recentViewers = [];
    } else if (platform === 'twitch' && twitchClient) {
        await twitchClient.disconnect();
        twitchClient = null;
        recentViewers = [];
    }
    res.json({ success: true });
});

app.post('/shutdown', (req, res) => {
    res.send('Shutting down...');
    shutdown();
});

// Store recent viewer info for overlay
// let recentViewers = []; // <-- REMOVE THIS LINE

function addRecentViewer(name, platform) {
    // Remove if already exists
    recentViewers = recentViewers.filter(v => v.name !== name);
    // Add to end
    recentViewers.push({ name, platform, color: platform === 'tiktok' ? '#00b400' : '#9146ff' });
    // Limit to 100
    if (recentViewers.length > 100) recentViewers.shift();
}

// Patch chat events to record platform
// (Insert this logic in TikTok and Twitch chat handlers)
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'overlay.html'));
});
app.get('/recent-viewers', (req, res) => {
    // viewersSet stores nicknames now, so return as is
    res.json({ viewers: Array.from(viewersSet) });
});

app.get('/overlay-viewers', (req, res) => {
    // Return the recent viewers as array of {name, platform, color}
    res.json({ viewers: recentViewers });
});

app.get('/health', (req, res) => {
    res.status(200).json({ status: 'ok' });
});
