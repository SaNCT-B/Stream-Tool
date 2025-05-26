# Stream Tool

**Stream Tool** is a desktop application for TikTok and Twitch streamers. It listens to chat for a specific keyword and logs unique viewer names in real-time.

This tool includes:
- A **Python GUI** built with Tkinter  
- A **Node.js server** that handles WebSocket and platform connection logic

---

## 👤 For Users

### ❓ How to Use

1. Download the latest `StreamTool.zip` from the [Releases](https://github.com/SaNCT-B/Stream-Tool/releases)
2. Extract the contents to a folder
3. Double-click:
   - `Stream Tool.exe` → launches the main app
   - `server.exe` → backend server (launched automatically by the app)

> 💡 You may be prompted to allow Node.js to run — click "Allow" if so.

---

## 🛠 For Developers

### 📦 Requirements

Make sure you have the following installed:

- **Python 3.10+**
- **Node.js v18+**
- **Python packages:**

  ```bash
  pip install pyinstaller websocket-client requests
  ```

- **(Optional but recommended)** Node packager:

  ```bash
  npm install -g pkg
  ```

---

### ⚙️ Build the Application

To clean and rebuild the application from source:

1. Open a terminal  
2. Navigate to the `scripts/` folder  
3. Run the installer script:

   ```bash
   build_installer.bat
   ```

This will:

- Clean previous builds (`build/`, `dist/`, cache files)
- Run `npm install` to restore Node dependencies
- Compile `server.js` into `dist/server.exe` using `pkg`
- Build the Python GUI into `dist/Stream Tool.exe` using PyInstaller

📁 After the script runs, your fully compiled app will be ready in the `/dist` folder.
