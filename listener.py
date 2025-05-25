import websocket
import threading
import logging
import time
import json  # Add this at the top with other imports

# Configure logging to only show WARNING and above
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

    def on_message(self, ws, message):  # Fixed indentation - this is a class method
        # Handle plain text control messages first
        if message in ['clearViewers', 'disconnect']:
            if self.message_callback:
                self.message_callback(message)
            return

        try:
            data = json.loads(message)
            if data.get("type") == "chat":
                if self.message_callback:
                    self.message_callback(message)
        except json.JSONDecodeError:
            # Only log if it's not a known control message
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
        logger.error(f"❌ WebSocket error: {error}")
        if self.status_callback:
            self.status_callback(f"❌ WebSocket Error: {error}", "red")

    def on_close(self, ws, close_status_code, close_msg):
        self.connected = False
        print("🔴 WebSocket connection closed")
        if self.status_callback:
            self.status_callback("🔴 WebSocket Disconnected", "red")

    def connect(self):
        if self.connected:
            print("WebSocket already connected")
            return

        if self.ws:
            self.ws.close()
            self.ws = None

        try:
            if self.status_callback:
                self.status_callback("⏳ Attempting to connect...", "orange")

            self.ws = websocket.WebSocketApp(
                f"ws://localhost:{self.port}",
                on_message=self.on_message,
                on_open=self.on_open,
                on_error=self.on_error,
                on_close=self.on_close
            )

            def run_websocket():
                self.ws.run_forever(ping_interval=30, ping_timeout=10)

            self.ws_thread = threading.Thread(target=run_websocket, daemon=True)
            self.ws_thread.start()

        except Exception as e:
            print(f"WebSocket connection error: {e}")
            if self.status_callback:
                self.status_callback(f"❌ WebSocket connection failed: {e}", "red")

    def disconnect(self):
        if self.ws:
            self.ws.close()
            self.ws = None
        self.connected = False

    def retry_connection(self):
        self.disconnect()
        time.sleep(1)  # Short delay before reconnecting
        self.connect()

def create_listener(port, message_callback=None, status_callback=None):
    """Factory function to create and start a WebSocket listener"""
    ws_manager = WebSocketManager(port, message_callback, status_callback)
    ws_manager.connect()
    return ws_manager

# Global reference to the GUI