import sys
import os
import subprocess
import tkinter as tk
from tkinter import messagebox, filedialog, scrolledtext
import requests
import threading
import time
import unicodedata
import re
import json
from listener import create_listener

class UsernameCompiler:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()  # Hide window until everything is set up
        self.root.title("Stream Tool")
        
        # Initialize instance variables
        self.ws_manager = None
        self.server_process = None
        self.viewer_set = set()
        self.nickname_map = {}
        self.current_display_mode = "Unsanitized Names"
        
        self.setup_gui()
        self.setup_event_handlers()
        
        # Update initial status to show attempting to connect
        self.status_label.config(text="⏳ Attempting to connect...", fg="orange")
        
        # After GUI is set up, get initial window size
        self.root.update_idletasks()  # Ensure all widgets are rendered
        initial_width = self.root.winfo_width()
        initial_height = self.root.winfo_height()
        
        # Set minimum size to prevent window becoming smaller than initial size
        self.root.minsize(initial_width, initial_height)
        
        # Finish setup and show GUI after everything is ready
        self.root.after(100, self.finish_startup)

    def setup_gui(self):
        # Create GUI components...
        # (Keep your existing GUI setup code here, but remove WebSocket-specific parts)
        port_frame = tk.Frame(self.root)
        port_frame.pack(pady=5)

        tk.Label(port_frame, text="Port:").pack(side=tk.LEFT)
        self.port_entry = tk.Entry(port_frame, width=6)
        self.port_entry.insert(0, "8080")  # Default port
        self.port_entry.pack(side=tk.LEFT, padx=5)

        tk.Button(port_frame, text="Submit", command=lambda: self.submit_port()).pack(side=tk.LEFT, padx=5)
        self.port_entry.bind("<Return>", lambda event: self.submit_port())

        divider0 = tk.Frame(self.root, bg="black", height=2)
        divider0.pack(fill=tk.X, pady=10)

        form_frame = tk.Frame(self.root)
        form_frame.pack()

        tiktok_column = tk.Frame(form_frame)
        tiktok_column.pack(side=tk.LEFT, padx=10)

        tk.Label(tiktok_column, text="TikTok Username:").pack()
        self.tiktok_entry = tk.Entry(tiktok_column, width=25)
        self.tiktok_entry.pack()
        self.tiktok_entry.bind("<Return>", lambda event: self.submit_username("tiktok"))

        tiktok_frame = tk.Frame(tiktok_column)
        tiktok_frame.pack(pady=(5, 10))
        tk.Button(tiktok_frame, text="Submit", command=lambda: self.submit_username("tiktok")).pack(side=tk.LEFT, padx=5)
        tk.Button(tiktok_frame, text="Clear", command=lambda: self.clear_username("tiktok")).pack(side=tk.LEFT, padx=5)
        self.tiktok_status_label = tk.Label(tiktok_column, text="", anchor="w", fg="red")
        self.tiktok_status_label.pack()

        twitch_column = tk.Frame(form_frame)
        twitch_column.pack(side=tk.LEFT, padx=10)

        tk.Label(twitch_column, text="Twitch Username:").pack()
        self.twitch_entry = tk.Entry(twitch_column, width=25)
        self.twitch_entry.pack()
        self.twitch_entry.bind("<Return>", lambda event: self.submit_username("twitch"))

        twitch_frame = tk.Frame(twitch_column)
        twitch_frame.pack(pady=(5, 10))
        tk.Button(twitch_frame, text="Submit", command=lambda: self.submit_username("twitch")).pack(side=tk.LEFT, padx=5)
        tk.Button(twitch_frame, text="Clear", command=lambda: self.clear_username("twitch")).pack(side=tk.LEFT, padx=5)
        self.twitch_status_label = tk.Label(twitch_column, text="", anchor="w", fg="red")
        self.twitch_status_label.pack()

        keyword_row = tk.Frame(self.root)
        keyword_row.pack(pady=(10, 0))

        tk.Label(keyword_row, text="Keyword (case-insensitive):").pack()
        self.keyword_entry = tk.Entry(keyword_row, width=40)
        self.keyword_entry.pack()
        self.keyword_entry.bind("<Return>", lambda event: self.submit_keyword())

        keyword_frame = tk.Frame(keyword_row)
        keyword_frame.pack(pady=(5, 10))

        tk.Button(keyword_frame, text="Submit", command=self.submit_keyword).pack(side=tk.LEFT, padx=5)
        tk.Button(keyword_frame, text="Clear", command=self.clear_keyword).pack(side=tk.LEFT, padx=5)
        self.keyword_status_label = tk.Label(keyword_row, text="", anchor="w", fg="red")
        self.keyword_status_label.pack()

        divider1 = tk.Frame(self.root, bg="black", height=2)
        divider1.pack(fill=tk.X, pady=10)

        tk.Label(self.root, text="Display Format:").pack()
        name_button_frame = tk.Frame(self.root)
        name_button_frame.pack(pady=5)

        tk.Button(name_button_frame, text="Unsanitized Names", command=self.show_unsanitized_names).pack(side=tk.LEFT, padx=5)
        tk.Button(name_button_frame, text="Sanitized Names", command=self.show_sanitized_name).pack(side=tk.LEFT, padx=5)
        tk.Button(name_button_frame, text="First Word Only", command=self.show_first_word).pack(side=tk.LEFT, padx=5)

        divider2 = tk.Frame(self.root, bg="black", height=2)
        divider2.pack(fill=tk.X, pady=10)

        tk.Label(self.root, text="Viewer Names:").pack()
        self.viewer_text = ViewerList(self.root, height=10, width=50, bg='white')
        self.viewer_text.pack()

        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(pady=10)

        tk.Button(bottom_frame, text="Copy List", command=self.copy_list).pack(side=tk.LEFT, padx=5)
        tk.Button(bottom_frame, text="Save List", command=self.save_to_file).pack(side=tk.LEFT, padx=5)
        tk.Button(bottom_frame, text="Clear All", command=self.clear_all).pack(side=tk.LEFT, padx=5)

        self.retry_button = tk.Button(bottom_frame, text="Reconnect", command=self.retry_ws, state=tk.DISABLED)
        self.status_label = tk.Label(self.root, text="🔴 Not connected", anchor="center", justify="center", fg="red")
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(10, 5))
        self.retry_button.pack(side=tk.LEFT, padx=5)

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
                    
                    start_index = self.viewer_text.index("end-1c")
                    self.viewer_text.insert(tk.END, nickname)
                    end_index = self.viewer_text.index("end-1c")
                    
                    if platform == "tiktok":
                        self.viewer_text.tag_add("tiktok", start_index, end_index)
                    elif platform == "twitch":
                        self.viewer_text.tag_add("twitch", start_index, end_index)
                    
                    self.viewer_text.see(tk.END)
                    
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

    def update_status(self, message, color):
        self.status_label.config(text=message, fg=color)

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
        self.restart_backend(port)
        self.root.deiconify()  # Show the window after full setup


    def retry_ws(self):
        if self.ws_manager:
            self.retry_button.config(state=tk.DISABLED)
            self.update_status("⏳ Retrying WebSocket connection...", "blue")
            self.ws_manager.retry_connection()

    def on_close_window(self):
        try:
            if self.ws_manager:
                self.ws_manager.disconnect()
            
            if self.server_process:
                self.server_process.terminate()
                self.server_process.wait(timeout=5)
        except Exception as e:
            print(f"Error during cleanup: {e}")
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

        try:
            port = self.port_entry.get()
            res = requests.post(f"http://localhost:{port}/start", json={"username": username, "platform": platform})
            data = res.json()

            if res.status_code == 200 and data.get("success") == True:
                status_label.config(text=f"Connected: @{username}", fg="green")
            else:
                error_msg = data.get("error", "Connection failed")
                status_label.config(text=error_msg, fg="red")
        except Exception as e:
            status_label.config(text=f"Could not connect: {str(e)}", fg="red")

    def clear_username(self, platform):
        entry = self.tiktok_entry if platform == "tiktok" else self.twitch_entry
        status_label = self.tiktok_status_label if platform == "tiktok" else self.twitch_status_label
        entry.delete(0, tk.END)
        status_label.config(text="", fg="red")

        try:
            port = self.port_entry.get()
            requests.post(f"http://localhost:{port}/disconnect", json={"platform": platform})
        except Exception:
            pass

    def submit_keyword(self):
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
        except Exception:
            self.update_keyword_status("❌ Could not reach server", "red")

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
            pass

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
            sanitized = self.sanitize_name(name).capitalize()
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
                first_word = cleaned.split()[0].capitalize()
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
                return sanitized_name.split()[0].capitalize()
        elif self.current_display_mode == "Sanitized Names":
            sanitized_name = self.sanitize_name(name)
            if sanitized_name:
                return sanitized_name.capitalize()
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
            
            def wait_for_port(port, timeout=10):  # Increased timeout
                start = time.time()
                retry_interval = 0.5  # Half second between retries
                
                while time.time() - start < timeout:
                    try:
                        # Try to make an HTTP request to the server
                        requests.get(f"http://localhost:{port}/health", timeout=1)
                        print("Server started successfully on port", port)
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
            return None

class ViewerList(scrolledtext.ScrolledText):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.tag_configure("tiktok", foreground="#00b400")  # Dark green
        self.tag_configure("twitch", foreground="#9146ff")  # Twitch purple
        self.original_names = []  # Store original names and their platforms

    def add_viewer(self, name, platform):
        # Store original name and platform when adding new viewer
        self.original_names.append((name, platform))
        
        # Add to display with appropriate tag
        if self.get("1.0", tk.END).strip():
            self.insert(tk.END, ", ")
        start = self.index("end-1c")
        self.insert(tk.END, name)
        end = self.index("end-1c")
        self.tag_add(platform, start, end)

def handle_websocket_message(self, message):
    if message == 'clearViewers':
        self.viewer_text.delete("1.0", tk.END)
        self.viewer_set.clear()
        self.nickname_map.clear()
        self.viewer_text.original_names = []  # Clear original names too
        return

    try:
        data = json.loads(message)
        if data.get("type") == "chat":
            nickname = data.get("viewerName", "").strip()
            platform = data.get("platform", "")
            
            if nickname and nickname not in self.viewer_set:
                self.viewer_set.add(nickname)
                # Store original name and platform
                self.viewer_text.original_names.append((nickname, platform))
                
                # Format display based on current mode
                display_name = nickname
                if self.current_display_mode == "Sanitized Names":
                    display_name = self.sanitize_name(nickname).capitalize()
                elif self.current_display_mode == "First Word Only":
                    display_name = self.sanitize_name(nickname).split()[0].capitalize()
                
                current_text = self.viewer_text.get("1.0", tk.END).strip()
                if current_text:
                    self.viewer_text.insert(tk.END, ", ")
                
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
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    app = UsernameCompiler()
    app.run()
