import websocket
import threading
import logging
import time
import json

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self, port, message_callback=None, status_callback=None):
        self.port = port
        self.ws = None
        self.connected = False
        self.message_callback = message_callback
        self.status_callback = status_callback
        self.ws_thread = None

    def on_message(self, ws, message):
        if message in ['clearViewers', 'disconnect']:
            if self.message_callback:
                self.message_callback(message)
            return

        try:
            data = json.loads(message)
            if data.get("type") == "chat" and self.message_callback:
                self.message_callback(message)
        except json.JSONDecodeError:
            if message not in ['clearViewers', 'disconnect']:
                logger.error(f"❌ Failed to decode message: {message}")
        except Exception as e:
            logger.error(f"❌ WebSocket error: {e}")

    def on_open(self, ws):
        self.connected = True
        print("✅ WebSocket connected")
        if self.status_callback:
            self.status_callback("✅ WebSocket Connected", "green")

    def on_error(self, ws, error):
        self.connected = False
        logger.error(f"❌ WebSocket error: {error}")
        if self.status_callback:
            self.status_callback(f"❌ WebSocket Error: {error}", "red")

    def on_close(self, ws, close_status_code, close_msg):
        self.connected = False
        print("🔴 WebSocket connection closed")
        if self.status_callback:
            self.status_callback("🔴 WebSocket Disconnected", "red")

    def connect(self, retries=2):
        if self.connected:
            print("WebSocket already connected")
            return

        attempt = 0
        while attempt <= retries:
            if self.ws:
                self.ws.close()
                self.ws = None

            try:
                if self.status_callback:
                    self.status_callback(f"⏳ Connecting (attempt {attempt + 1})...", "orange")

                self.ws = websocket.WebSocketApp(
                    f"ws://localhost:{self.port}",
                    on_message=self.on_message,
                    on_open=self.on_open,
                    on_error=self.on_error,
                    on_close=self.on_close
                )

                def run_ws():
                    self.ws.run_forever(ping_interval=30, ping_timeout=10)

                self.ws_thread = threading.Thread(target=run_ws, daemon=True)
                self.ws_thread.start()

                # Wait briefly to see if it connects
                for _ in range(20):  # wait up to 2 seconds
                    if self.connected:
                        return
                    time.sleep(0.1)

            except Exception as e:
                logger.error(f"WebSocket connection attempt failed: {e}")

            attempt += 1
            time.sleep(1.5 ** attempt)

        if self.status_callback:
            self.status_callback("❌ Failed to connect after retries", "red")

    def disconnect(self):
        if self.ws:
            self.ws.close()
            self.ws = None
        self.connected = False

    def retry_connection(self):
        self.disconnect()
        time.sleep(1)
        self.connect()

def create_listener(port, message_callback=None, status_callback=None):
    ws_manager = WebSocketManager(port, message_callback, status_callback)
    threading.Thread(target=ws_manager.connect, daemon=True).start()
    return ws_manager
