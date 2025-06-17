import sys
import os
import subprocess
import time
import re
import json
import unicodedata
import threading

import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext

import requests

from listener import create_listener

ERROR_LOG = 'error_output.log'
# Overwrite error log at startup
with open(ERROR_LOG, 'w', encoding='utf-8') as f:
    pass
def log_error(err):
    try:
        with open(ERROR_LOG, 'a', encoding='utf-8') as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {err}\n")
    except Exception:
        pass

class UsernameCompiler:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("Stream Tool")

        self.ws_manager = None
        self.server_process = None
        self.viewer_set = set()
        self.nickname_map = {}
        self.current_display_mode = "Unsanitized Names"
        self.keyword_hidden = False

        self.setup_gui()
        self.setup_event_handlers()

        self.status_label.config(text="⏳ Attempting to connect...", fg="orange")

        self.root.update_idletasks()
        self.root.minsize(self.root.winfo_width(), self.root.winfo_height())

        threading.Thread(target=self.finish_startup, daemon=True).start()

    def setup_gui(self):
        def make_button(parent, text, cmd):
            return tk.Button(parent, text=text, command=cmd)

        port_frame = tk.Frame(self.root)
        port_frame.pack(pady=5)
        tk.Label(port_frame, text="Port:").pack(side=tk.LEFT)
        self.port_entry = tk.Entry(port_frame, width=6)
        self.port_entry.insert(0, "8080")
        self.port_entry.pack(side=tk.LEFT, padx=5)
        make_button(port_frame, "Submit", self.submit_port).pack(side=tk.LEFT, padx=5)
        self.port_entry.bind("<Return>", lambda e: self.submit_port())

        tk.Frame(self.root, bg="black", height=2).pack(fill=tk.X, pady=10)

        form_frame = tk.Frame(self.root)
        form_frame.pack()

        self._setup_platform_column(form_frame, "TikTok")
        self._setup_platform_column(form_frame, "Twitch")

        keyword_row = tk.Frame(self.root)
        keyword_row.pack(pady=(10, 0))
        tk.Label(keyword_row, text="Keyword (case-insensitive):").pack()

        self.keyword_entry_container = tk.Frame(keyword_row)
        self.keyword_entry_container.pack()
        self.keyword_entry = tk.Entry(self.keyword_entry_container, width=30, font=("Arial", 11))
        self.keyword_entry.pack()
        self.keyword_overlay = tk.Label(self.keyword_entry_container, bg="lightgray", width=40, height=1)
        self.keyword_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.keyword_overlay.lower()
        self.keyword_entry.bind("<Return>", lambda e: self.submit_keyword())

        keyword_frame = tk.Frame(self.root)
        keyword_frame.pack(pady=(5, 10))
        make_button(keyword_frame, "Submit", self.submit_keyword).pack(side=tk.LEFT, padx=5)
        make_button(keyword_frame, "Clear", self.clear_keyword).pack(side=tk.LEFT, padx=5)
        self.toggle_keyword_btn = tk.Button(keyword_frame, text="Hide", width=7, command=self.toggle_keyword_visibility)
        self.toggle_keyword_btn.pack(side=tk.LEFT, padx=5)

        self.keyword_status_label = tk.Label(self.root, text="", anchor="w", fg="red")
        self.keyword_status_label.pack()
        self.keyword_label_overlay = tk.Label(self.root, bg="lightgray")
        self.keyword_label_overlay.lower()
        self.root.after(200, self._place_keyword_label_overlay)

        tk.Frame(self.root, bg="black", height=2).pack(fill=tk.X, pady=10)
        tk.Label(self.root, text="Display Format:").pack()
        name_button_frame = tk.Frame(self.root)
        name_button_frame.pack(pady=5)

        make_button(name_button_frame, "Unsanitized Names", self.show_unsanitized_names).pack(side=tk.LEFT, padx=5)
        make_button(name_button_frame, "Sanitized Names", self.show_sanitized_name).pack(side=tk.LEFT, padx=5)
        make_button(name_button_frame, "First Word Only", self.show_first_word).pack(side=tk.LEFT, padx=5)

        tk.Frame(self.root, bg="black", height=2).pack(fill=tk.X, pady=10)
        tk.Label(self.root, text="Viewer Names:").pack()
        self.viewer_text = ViewerList(self.root, height=10, width=50, bg='white')
        self.viewer_text.original_names = []
        self.viewer_text.pack()

        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(pady=10)
        make_button(bottom_frame, "Copy List", self.copy_list).pack(side=tk.LEFT, padx=5)
        make_button(bottom_frame, "Save List", self.save_to_file).pack(side=tk.LEFT, padx=5)
        make_button(bottom_frame, "Clear All", self.clear_all).pack(side=tk.LEFT, padx=5)

        self.retry_button = make_button(bottom_frame, "Reconnect", self.retry_ws)
        self.retry_button.config(state=tk.DISABLED)
        self.retry_button.pack(side=tk.LEFT, padx=5)

        self.status_label = tk.Label(self.root, text="🔴 Not connected", anchor="center", justify="center", fg="red")
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(10, 5))

    def _place_keyword_label_overlay(self):
        try:
            x = self.keyword_status_label.winfo_rootx() - self.root.winfo_rootx()
            y = self.keyword_status_label.winfo_rooty() - self.root.winfo_rooty()
            w = self.keyword_status_label.winfo_width()
            h = self.keyword_status_label.winfo_height()
            self.keyword_label_overlay.place(x=x, y=y, width=w, height=h)
        except Exception as e:
            print("Overlay error:", e)
            log_error(e)

    def _setup_platform_column(self, parent, platform):
        lower = platform.lower()
        column = tk.Frame(parent)
        column.pack(side=tk.LEFT, padx=10)
        tk.Label(column, text=f"{platform} Username:").pack()
        entry = tk.Entry(column, width=20, font=("Arial", 11))
        entry.pack()
        entry.bind("<Return>", lambda e: self.submit_username(lower))

        frame = tk.Frame(column)
        frame.pack(pady=(5, 10))
        tk.Button(frame, text="Submit", command=lambda: self.submit_username(lower)).pack(side=tk.LEFT, padx=5)
        tk.Button(frame, text="Clear", command=lambda: self.clear_username(lower)).pack(side=tk.LEFT, padx=5)

        label = tk.Label(column, text="", anchor="w", fg="red")
        label.pack()

        if lower == "tiktok":
            self.tiktok_entry = entry
            self.tiktok_status_label = label
        else:
            self.twitch_entry = entry
            self.twitch_status_label = label

    def setup_event_handlers(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_window)

    def handle_websocket_message(self, message):
        if message == 'clearViewers':
            self.viewer_text.delete("1.0", tk.END)
            self.viewer_set.clear()
            self.nickname_map.clear()
            self.viewer_text.original_names = []  # Reset original names
            return

        try:
            data = json.loads(message)
            if data.get("type") == "chat":
                nickname = data.get("viewerName", "").strip()
                platform = data.get("platform", "")
                
                if nickname and nickname not in self.viewer_set:
                    self.viewer_set.add(nickname)
                    # Store the original name and platform
                    if not hasattr(self.viewer_text, 'original_names'):
                        self.viewer_text.original_names = []
                    self.viewer_text.original_names.append((nickname, platform))
                    
                    current_text = self.viewer_text.get("1.0", tk.END).strip()
                    if current_text:
                        self.viewer_text.insert(tk.END, ", ")
                    
                    display_name = self.get_display_name(nickname)
                    start_index = self.viewer_text.index("end-1c")
                    self.viewer_text.insert(tk.END, display_name)
                    end_index = self.viewer_text.index("end-1c")

                    if platform == "tiktok":
                        self.viewer_text.tag_add("tiktok", start_index, end_index)
                    elif platform == "twitch":
                        self.viewer_text.tag_add("twitch", start_index, end_index)
                    
                    self.viewer_text.see(tk.END)
                    
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            log_error(e)
        except Exception as e:
            print(f"Unexpected error: {e}")
            log_error(e)

    def get_display_name(self, name):
        if self.current_display_mode == "Sanitized Names":
            return self.sanitize_name(name)
        elif self.current_display_mode == "First Word Only":
            sanitized = self.sanitize_name(name)
            if sanitized:
                return sanitized.split()[0]
            return ""
        elif self.current_display_mode == "Unsanitized Names":
            return name
        return name


    def update_status(self, message, color):
        self.status_label.config(text=message, fg=color)
        # Enable the button if not connected, disable if connected
        if any(word in message for word in ["Disconnected", "Error", "failed"]):
            self.retry_button.config(state=tk.NORMAL)
        elif any(word in message for word in ["connected", "Started server", "Listening"]):
            self.retry_button.config(state=tk.DISABLED)

    def restart_backend(self, port):
        # Cleanup existing connections
        if self.ws_manager:
            self.ws_manager.disconnect()

        if self.server_process:
            self.server_process.terminate()

        # Start new server process
        self.server_process = self.start_server(port)
        if not self.server_process:
            self.update_status("Failed to start server", "red")
            return

        # Create new WebSocket connection
        self.ws_manager = create_listener(
            port=port,
            message_callback=self.handle_websocket_message,
            status_callback=self.update_status
        )

    def finish_startup(self):
        try:
            port = int(self.port_entry.get() or 8080)
        except ValueError:
            port = 8080
        self.update_status("⏳ Starting server...", "orange")
        self.root.after(100, lambda: self._defer_startup(port))

    def _defer_startup(self, port):
        self.restart_backend(port)
        self.root.deiconify()

    def retry_ws(self):
        if self.ws_manager:
            self.update_status("⏳ Restarting server and reconnecting...", "blue")
            self.restart_server()
            time.sleep(2)  # wait a bit for the server to boot
        # Wait for WebSocket to reconnect and update status to green if successful
        def wait_for_ws():
            for _ in range(30):  # wait up to 3 seconds
                if self.ws_manager and getattr(self.ws_manager, 'connected', False):
                    self.update_status("🟢 Connected", "green")
                    return
                time.sleep(0.1)
        threading.Thread(target=wait_for_ws, daemon=True).start()

    def on_close_window(self):
        try:
            if self.ws_manager:
                self.ws_manager.disconnect()
            
            if self.server_process:
                self.server_process.terminate()
                self.server_process.wait(timeout=5)
        except Exception as e:
            print(f"Error during cleanup: {e}")
            log_error(e)
        finally:
            self.root.destroy()

    def run(self):
        self.root.mainloop()

    def submit_port(self):
        port = self.port_entry.get().strip()
        if not port:
            messagebox.showerror("Error", "Port is required.")
            return
        self.update_status(f"Restarting on port {port}...", "orange")
        self.restart_backend(int(port)) 

    def submit_username(self, platform):
        entry = self.tiktok_entry if platform == "tiktok" else self.twitch_entry
        status_label = self.tiktok_status_label if platform == "tiktok" else self.twitch_status_label

        username = entry.get().strip()
        if not username:
            status_label.config(text="Streamer username is required.", fg="red")
            return

        username = username.lstrip("@")
        label_display = f"@{username}" if platform == "tiktok" else username

        status_label.config(text="⏳ Connecting...", fg="orange")

        # 🧵 Run connection in background thread to avoid UI freeze
        thread = threading.Thread(
            target=lambda: self._submit_username_thread(platform, username, label_display, status_label),
            daemon=True
        )
        thread.start()

    def _submit_username_thread(self, platform, username, label_display, status_label):
        try:
            port = self.port_entry.get()
            res = requests.post(
                f"http://localhost:{port}/start",
                json={"username": username, "platform": platform},
                timeout=5
            )
            data = res.json()

            def update_status():
                if res.status_code == 200 and data.get("success") is True:
                    status_label.config(text=f"Connected: {label_display}", fg="green")
                elif res.status_code == 400:
                    status_label.config(text="🔴 User is not live", fg="red")
                elif res.status_code == 503:
                    status_label.config(text="⚠️ TikTok sign server failed (504). Try again shortly.", fg="orange")
                else:
                    status_label.config(text="❌ Failed to connect", fg="red")

            self.root.after(0, update_status)

        except Exception as e:
            log_error(e)
            self.root.after(0, lambda: status_label.config(
                text=f"Could not connect", fg="red"
            ))


    def clear_username(self, platform):
        entry = self.tiktok_entry if platform == "tiktok" else self.twitch_entry
        status_label = self.tiktok_status_label if platform == "tiktok" else self.twitch_status_label
        entry.delete(0, tk.END)
        status_label.config(text="", fg="red")

        try:
            port = self.port_entry.get()
            requests.post(f"http://localhost:{port}/disconnect", json={"platform": platform})
        except Exception as e:
            log_error(e)
            pass

    def submit_keyword(self):
        self.clear_viewers()
        keyword = self.keyword_entry.get().strip()
        if not keyword:
            self.update_keyword_status("Keyword is required.", "red")
            return
        try:
            port = self.port_entry.get()
            res = requests.post(f"http://localhost:{port}/keyword", json={"keyword": keyword})
            if res.ok:
                # Clear everything when setting a new keyword
                self.viewer_text.delete("1.0", tk.END)
                self.viewer_set.clear()  # Clear the set of tracked viewers
                self.nickname_map.clear()
                
                # Remove all existing color tags
                for tag in ["tiktok", "twitch"]:
                    self.viewer_text.tag_remove(tag, "1.0", tk.END)
                    
                self.update_keyword_status(f"Keyword set: {keyword}", "green")
            else:
                self.update_keyword_status("❌ Failed to set keyword", "red")
        except Exception as e:
            log_error(e)
            self.update_keyword_status("❌ Could not reach server", "red")

    def clear_viewers(self):
        self.viewer_text.delete("1.0", tk.END)
        self.viewer_set.clear()
        self.nickname_map.clear()
        self.viewer_text.original_names = []

    def clear_keyword(self):
        self.keyword_entry.delete(0, tk.END)
        self.update_keyword_status("", "red")
        self.viewer_text.delete("1.0", tk.END)
        self.viewer_set.clear()  # Clear the set of tracked viewers
        self.nickname_map.clear()
        
        # Send clearViewers message to server to reset its tracking
        try:
            port = self.port_entry.get()
            requests.post(f"http://localhost:{port}/clearKeyword")
            
            # Clear all text tags
            for tag in ["tiktok", "twitch"]:
                self.viewer_text.tag_remove(tag, "1.0", tk.END)
                
        except Exception as e:
            print(f"Error clearing keyword: {e}")
            log_error(e)
            pass

    def toggle_keyword_visibility(self):
        self.keyword_hidden = not self.keyword_hidden

        if self.keyword_hidden:
            self.toggle_keyword_btn.config(text="Unhide")
            self.keyword_overlay.lift()
            try:
                x = self.keyword_status_label.winfo_rootx() - self.root.winfo_rootx()
                y = self.keyword_status_label.winfo_rooty() - self.root.winfo_rooty()
                w = self.keyword_status_label.winfo_width()
                h = self.keyword_status_label.winfo_height()
                self.keyword_label_overlay.place(x=x, y=y, width=w, height=h)
                self.keyword_label_overlay.lift()
            except Exception as e:
                print("Toggle overlay error:", e)
                log_error(e)
        else:
            self.toggle_keyword_btn.config(text="Hide")
            self.keyword_overlay.lower()
            self.keyword_label_overlay.place_forget()

    def update_keyword_status(self, text, color="red"):
        self.keyword_status_label.config(text=text, fg=color)

    def show_unsanitized_names(self):
        self.current_display_mode = "Unsanitized Names"
        if not hasattr(self.viewer_text, 'original_names') or not self.viewer_text.original_names:
            return
            
        self.viewer_text.delete("1.0", tk.END)
        for i, (name, platform) in enumerate(self.viewer_text.original_names):
            if i > 0:
                self.viewer_text.insert(tk.END, ", ")
            start = self.viewer_text.index("end-1c")
            self.viewer_text.insert(tk.END, name)
            end = self.viewer_text.index("end-1c")
            self.viewer_text.tag_add(platform, start, end)

    def show_sanitized_name(self):
        self.current_display_mode = "Sanitized Names"
        if not hasattr(self.viewer_text, 'original_names') or not self.viewer_text.original_names:
            return
            
        self.viewer_text.delete("1.0", tk.END)
        for i, (name, platform) in enumerate(self.viewer_text.original_names):
            if i > 0:
                self.viewer_text.insert(tk.END, ", ")
            sanitized = self.sanitize_name(name)
            if sanitized:
                start = self.viewer_text.index("end-1c")
                self.viewer_text.insert(tk.END, sanitized)
                end = self.viewer_text.index("end-1c")
                self.viewer_text.tag_add(platform, start, end)

    def show_first_word(self):
        self.current_display_mode = "First Word Only"
        if not hasattr(self.viewer_text, 'original_names') or not self.viewer_text.original_names:
            return
            
        seen = set()
        self.viewer_text.delete("1.0", tk.END)
        for i, (name, platform) in enumerate(self.viewer_text.original_names):
            cleaned = self.sanitize_name(name)
            if cleaned:
                first_word = cleaned.split()[0]
                if first_word not in seen:
                    seen.add(first_word)
                    if i > 0 and self.viewer_text.get("1.0", tk.END).strip():
                        self.viewer_text.insert(tk.END, ", ")
                    start = self.viewer_text.index("end-1c")
                    self.viewer_text.insert(tk.END, first_word)
                    end = self.viewer_text.index("end-1c")
                    self.viewer_text.tag_add(platform, start, end)

    def format_name_for_display(self, name):
        if self.current_display_mode == "First Word Only":
            sanitized_name = self.sanitize_name(name)
            if sanitized_name:
                return sanitized_name.split()[0]
        elif self.current_display_mode == "Sanitized Names":
            sanitized_name = self.sanitize_name(name)
            if sanitized_name:
                return sanitized_name
        else:
            return name


    def update_viewer_list(self, new_name):
        formatted_name = self.format_name_for_display(new_name)

        if formatted_name and formatted_name not in self.viewer_set:
            self.viewer_set.add(formatted_name)

            current_text = self.viewer_text.get("1.0", tk.END).strip()

            if current_text:
                result = current_text + ", " + formatted_name
            else:
                result = formatted_name

            self.viewer_text.delete("1.0", tk.END)
            self.viewer_text.insert(tk.END, result)

            self.viewer_text.see(tk.END)

        self.viewer_text.update()

    def clear_text(self):
        self.viewer_set.clear()
        self.nickname_map.clear()
        self.viewer_text.delete("1.0", tk.END)

    def clear_all(self):
        self.clear_username("tiktok")
        self.clear_username("twitch")
        self.clear_keyword()

    def save_to_file(self):
        content = self.viewer_text.get("1.0", tk.END).strip()
        if not content:
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")])
        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

    def copy_list(self):
        content = self.viewer_text.get("1.0", tk.END).strip()
        if content:
            self.copy_to_clipboard(content)

    def copy_to_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def sanitize_name(self, name):
        cleaned = ''.join(
            c if unicodedata.category(c).startswith('L') or c.isspace() else ' '
            for c in unicodedata.normalize('NFKC', name)
        )
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    def start_server(self, port):
        try:
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
                server_path = os.path.join(base_path, 'server.exe')
                proc = subprocess.Popen([server_path, str(port)])
            else:
                base_path = os.path.dirname(os.path.abspath(__file__))
                server_path = os.path.join(base_path, 'server.js')
                proc = subprocess.Popen(["node", server_path, str(port)])

            print("Waiting for server to start...")
            
            def wait_for_port(port, timeout=8):
                start = time.time()
                retry_interval = 0.5  # Half second between retries
                
                while time.time() - start < timeout:
                    try:
                        # Try to make an HTTP request to the server
                        requests.get(f"http://localhost:{port}/health", timeout=1)
                        print("⚡Server started successfully on port", port)
                        return True
                    except requests.RequestException:
                        time.sleep(retry_interval)
                        continue
                return False

            if wait_for_port(port):
                return proc
            else:
                proc.terminate()
                print("Server failed to start within timeout period")
                return None

        except Exception as e:
            print("Failed to start server:", e)
            log_error(e)
            return None
        
    def restart_server(self):
        try:
            if self.server_process:
                self.server_process.terminate()
                self.server_process.wait()
            time.sleep(2)
            self.server_process = self.start_server(int(self.port_entry.get()))
        except Exception as e:
            log_error(e)
            self.update_status(f"❌ Error restarting server: {e}", "red")


class ViewerList(scrolledtext.ScrolledText):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.tag_configure("tiktok", foreground="#00b400")  # Dark green
        self.tag_configure("twitch", foreground="#9146ff")  # Twitch purple
        self.original_names = []  # Store original names and their platforms

def add_viewer(self, display_name, platform):
    if self.get("1.0", tk.END).strip():
        self.insert(tk.END, ", ")
    start = self.index("end-1c")
    self.insert(tk.END, display_name)
    end = self.index("end-1c")
    self.tag_add(platform, start, end)

if __name__ == "__main__":
    app = UsernameCompiler()
    app.run()
