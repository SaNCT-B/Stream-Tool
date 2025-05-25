# Stream Tool

**Stream Tool** is a desktop application for TikTok and Twitch streamers. It listens to chat for a specific keyword and logs unique viewer names in real-time.

This tool includes:
- A **Python GUI** built with Tkinter
- A **Node.js server** that handles WebSocket and platform connection logic

---

## 👤 For Users

### ✅ How to Use

1. Download the latest `.zip` from the [Releases](https://github.com/SaNCT-B/Stream-Tool/releases)
2. Extract the contents to a folder
3. Double-click:
   - `Stream Tool.exe` → launches the main app
   - `server.exe` → backend server (launched automatically by the app)

> 💡 You may be prompted to allow Node.js to run — click "Allow" if so.

---

## 🛠 For Developers

### 📦 Requirements

Make sure you have the following installed:

- [Python 3.10+](https://www.python.org/downloads/)
- [Node.js v18+](https://nodejs.org/)
- Python packages:
  ```bash
  pip install pyinstaller websocket-client requests
