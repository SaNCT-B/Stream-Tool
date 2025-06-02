const express = require('express');
const bodyParser = require('body-parser');
const WebSocket = require('ws');
const { WebcastPushConnection } = require('tiktok-live-connector');
const tmi = require('tmi.js');

const app = express();
const port = process.argv[2] || 8080; // Default port set to 8080

let currentKeyword = '';
let viewersSet = new Set();
let wsClient = null;

app.use(bodyParser.json());

const server = app.listen(port, () => {
    console.log(`🚀 Server is running on http://localhost:${port}`);
});

const shutdown = () => {
    console.log('🛑 Shutting down server...');
    if (tiktokConnection) {
        tiktokConnection.disconnect();
        console.log('🔌 TikTok connection closed');
    }
    if (wsClient) {
        wsClient.close();
        console.log('❌ WebSocket client closed');
    }
    server.close(() => {
        console.log('✅ HTTP server closed');
        process.exit(0);
    });
};

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

// WebSocket setup
const wss = new WebSocket.Server({ server });

// Heartbeat function to keep WebSocket alive
function heartbeat() {
    this.isAlive = true;
}

wss.on('connection', ws => {
    console.log('🔌 GUI connected via WebSocket');
    ws.isAlive = true;

    // Listen for pong messages to confirm the client is alive
    ws.on('pong', heartbeat);

    wsClient = ws;

    ws.on('close', () => {
        console.log('❌ GUI WebSocket disconnected');
        wsClient = null;
    });

    ws.on('error', error => {
        console.log(`❌ WebSocket error: ${error}`);
    });

    ws.onmessage = function(event) {
        const data = JSON.parse(event.data);
        if (data.type === 'chat') {
            // Apply the color style to the username
            const username = document.createElement('span');
            username.style.color = data.color;
            username.textContent = data.viewerName;
            
        }
    };
});

// Periodically check if WebSocket clients are alive
const interval = setInterval(() => {
    wss.clients.forEach(ws => {
        if (!ws.isAlive) {
            console.log('❌ Terminating unresponsive WebSocket client');
            return ws.terminate();
        }

        ws.isAlive = false;
        ws.ping(); // Send a ping to the client
    });
}, 30000); // Check every 30 seconds

// Cleanup interval on server shutdown
server.on('close', () => {
    clearInterval(interval);
});

function createKeywordMatcher(keyword) {
    const normalizeText = (text) => {
        return text.toLowerCase()
            .replace(/['']/g, "'")
            .replace(/\s+/g, ' ')
            .trim();
    };

    // Normalize input keyword
    const normalizedKeyword = normalizeText(keyword);
    
    // Check if keyword is only emojis
    const emojiRegex = /^[\u{1F300}-\u{1F9FF}]+$/u;
    if (emojiRegex.test(keyword)) {
        // If keyword is a single emoji, match only that emoji (repeated)
        return new RegExp(`^${keyword}+$`, 'u');
    }

    const words = normalizedKeyword.split(/\s+/);
    
    if (words.length > 1) {
        // Multi-word phrases
        const phrasePattern = words
            .map(word => {
                const baseWord = word.replace(/'/g, "");
                const escaped = baseWord.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                return escaped;
            })
            .join("[\\s']*"); // Allow spaces and apostrophes between words

        return new RegExp(
            `^${phrasePattern}[!.?]*(?:[\\u{1F300}-\\u{1F9FF}]+)?$`,
            'iu'
        );
    } else {
        // Single-word or single-letter case
        const baseWord = words[0].replace(/'/g, "");
        const escaped = baseWord.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        
        // Create pattern that allows letter repetition within the word
        const letterPattern = escaped.split('').map(char => {
            return `${char}+`;
        }).join('');

        return new RegExp(
            `^${letterPattern}[!.?]*(?:[\\u{1F300}-\\u{1F9FF}]+)?$`,
            'iu'
        );
    }
}

// Start TikTok connection
let tiktokConnection = null;
let twitchClient = null;

app.post('/start', async (req, res) => {
    const { username, platform } = req.body;

    if (!username || !platform) {
        return res.status(400).json({ success: false, error: "Missing username or platform" });
    }

    let responded = false;
    function sendOnce(statusCode, payload) {
        if (!responded) {
            responded = true;
            res.status(statusCode).json(payload);
        }
    }

    try {
        if (platform === "tiktok") {
            if (tiktokConnection) {
                tiktokConnection.disconnect();
            }

            tiktokConnection = new WebcastPushConnection(username);

            try {
                await tiktokConnection.connect();
                console.log(`Connected to TikTok user: ${username}`);

                const timeout = setTimeout(() => {
                    console.log("❌ No viewer data received, assuming user is not live.");
                    tiktokConnection.disconnect();
                    sendOnce(400, { success: false, error: "User is not live" });
                }, 5000);

                tiktokConnection.on('roomUser', (data) => {
                    const viewerCount = data?.viewerCount ?? 0;
                    if (wsClient && wsClient.readyState === WebSocket.OPEN) {
                        wsClient.send(JSON.stringify({
                            type: 'viewerCount',
                            platform: 'tiktok',
                            count: viewerCount
                        }));
                    }

                    if (!responded) {
                        clearTimeout(timeout);
                        sendOnce(200, { success: true });
                    }
                });

                tiktokConnection.once('streamEnd', () => {
                    console.log("🔴 Stream ended.");
                    clearTimeout(timeout);
                    tiktokConnection.disconnect();
                    sendOnce(400, { success: false, error: "User is not live" });
                });

                tiktokConnection.on('chat', (data) => {
                    const user = data.nickname || data.uniqueId || 'Unknown';
                    const text = data.comment || '';
                    console.log(`\x1b[32m[💬]\x1b[0m ${user}: \x1b[32m${text}\x1b[0m`);
                    if (currentKeyword) {
                        const matcher = createKeywordMatcher(currentKeyword);
                        if (matcher.test(text) && !viewersSet.has(user)) {
                            viewersSet.add(user);
                            if (wsClient && wsClient.readyState === WebSocket.OPEN) {
                                wsClient.send(JSON.stringify({
                                    type: 'chat',
                                    viewerName: user,
                                    message: text,
                                    platform: 'tiktok',
                                    color: '#00b400'
                                }));
                            }
                        }
                    }
                });

            } catch (err) {
                console.log("❌ Error connecting to TikTok:", err);
                sendOnce(400, { success: false, error: "User is not live" });
            }
            return;
        }

        if (platform === "twitch") {
            if (twitchClient) {
                await twitchClient.disconnect();
            }

            twitchClient = new tmi.Client({
                channels: [username]
            });

            twitchClient.on('message', (channel, tags, message, self) => {
                const user = tags['display-name'] || tags.username;
                console.log(`\x1b[35m[💬]\x1b[0m ${user}: \x1b[35m${message}\x1b[0m`);

                if (currentKeyword) {
                    const matcher = createKeywordMatcher(currentKeyword);
                    if (matcher.test(message)) {
                        if (!viewersSet.has(user)) {
                            viewersSet.add(user);
                            if (wsClient && wsClient.readyState === WebSocket.OPEN) {
                                wsClient.send(JSON.stringify({
                                    type: 'chat',
                                    viewerName: user,
                                    message: message,
                                    platform: 'twitch',
                                    color: '#9146ff'
                                }));
                            }
                        }
                    }
                }
            });

            await twitchClient.connect();
            console.log(`Connected to Twitch user: ${username}`);
            sendOnce(200, { success: true });
            return;
        }

        // If neither TikTok nor Twitch matched
        sendOnce(400, { success: false, error: "Unknown platform" });

    } catch (err) {
        console.error("❌ Error connecting to platform:", err);
        let errorMessage = "Unknown error";

        if (err?.reason === "Sign Error") {
            errorMessage = "❌ TikTok signing error, try again later.";
        } else if (err?.message?.includes("user_not_found")) {
            errorMessage = "❌ TikTok user not found or not live.";
        } else if (err?.message?.includes("ExtractRoomIdError")) {
            errorMessage = "❌ Could not extract Room ID. User may not be live.";
        } else if (err?.message) {
            errorMessage = err.message;
        }

        sendOnce(500, { success: false, error: errorMessage });
    }
});


// Set keyword
app.post('/keyword', (req, res) => {
    currentKeyword = req.body.keyword?.trim();
    viewersSet.clear();  // Clear the set when setting a new keyword
    console.log("🔑 Keyword set to:", currentKeyword);
    
    // Notify GUI to clear viewer list
    if (wsClient && wsClient.readyState === WebSocket.OPEN) {
        wsClient.send(JSON.stringify({
            type: 'control',
            action: 'clearViewers'
        }));
    }
    
    return res.json({ success: true });
});

// Reset keyword endpoint
app.post('/clearKeyword', (req, res) => {
    currentKeyword = '';
    viewersSet.clear();
    console.log('🔑 Keyword cleared');
    
    // Send reset message to GUI
    if (wsClient && wsClient.readyState === WebSocket.OPEN) {
        wsClient.send('clearViewers');
    }

    res.send('Keyword cleared');
});

app.post('/disconnect', async (req, res) => {
    const platform = req.body?.platform;

    if (platform === 'all') {
        if (tiktokConnection) {
            await tiktokConnection.disconnect();
            console.log("🔌 Disconnected from TikTok");
            tiktokConnection = null;
        }
        if (twitchClient) {
            await twitchClient.disconnect();
            console.log("🔌 Disconnected from Twitch");
            twitchClient = null;
        }
        // Send a structured JSON message instead of plain text
        if (wsClient && wsClient.readyState === WebSocket.OPEN) {
            wsClient.send(JSON.stringify({
                type: 'control',
                action: 'clearViewers'
            }));
        }
        currentKeyword = '';
        viewersSet.clear();
    } else if (platform === 'tiktok' && tiktokConnection) {
        await tiktokConnection.disconnect();
        console.log("🔌 Disconnected from TikTok");
        tiktokConnection = null;
    } else if (platform === 'twitch' && twitchClient) {
        await twitchClient.disconnect();
        console.log("🔌 Disconnected from Twitch");
        twitchClient = null;
    }

    res.json({ success: true });
});

// Shutdown endpoint
app.post('/shutdown', (req, res) => {
    res.send('Shutting down...');
    shutdown();
});

// Health check endpoint
app.get('/health', (req, res) => {
    res.status(200).json({ status: 'ok' });
});

