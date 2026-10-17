import sys
import os
import json
import uuid
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QPushButton, QTextEdit,
                             QLineEdit, QLabel, QVBoxLayout, QHBoxLayout, QScrollArea, QTextBrowser, 
                             QDialog, QSlider, QCheckBox, QRadioButton, QButtonGroup, QFileDialog)
from PyQt5.QtCore import QPropertyAnimation, Qt, QThread, pyqtSignal, QBuffer, QIODevice
from PyQt5.QtGui import QIcon, QTextCursor, QImage, QKeySequence
from searx_client import SearXClient
from file_loader import load_file, load_image_bytes, UnsupportedFile
from projects import ProjectsWindow
import requests
import subprocess
import time
import shutil
import html as html_module
import markdown
import re

# Project_Colors
GUNMETAL_GRAY = "#494d4a"
DEEP_CHARCOAL = "#363836"
BG_DARKMODE = "#2f302f"
ASH_GRAY = "#b0b8b2"
BG_LIGHTMODE = "#cfd1d0"
DEEP_BLACK = "#000501"
DEEP_PLUM = "#570148"
DEEP_RED = "#5c0101"
MUTED_ACCENT = "#947b7b"
DARK_ESPRESSO = "#332727"
BG_DARKMODE2 = "#111317"
MIDNIGHT_BLACK = "#191c21"

SYSTEM_PROMPT = """
    You are Qwen, a professional AI assistant.
    Your goals:
    - Give correct and factual answers.
    - Be concise unless the user requests details.
    - Explain difficult topics clearly.
    - Admit uncertainty instead of inventing facts.
    - Use Markdown when appropriate.
    - Format code inside code blocks.
    - Use bullet points and tables where appropriate.
    - Preserve context from conversation.
    - If the user asks for opinions, clearly separate facts from opinions.
    - If the user challenges an answer, re-check it against the available evidence. Agree only if the evidence supports them; otherwise explain why you disagree.
    - Only state a number, score or rating if a source gives it for the exact subject being discussed.
    - If you don't have enough information to answer confidently, say so directly instead of guessing.
    - Your knowledge has a cutoff. Things you don't recognize may simply be newer than your training - never claim something does not exist because you don't know about it.
"""

IMAGE_TOKEN_COST = 1100 # matches the --image-min-tokens 1024 floor

def count_tokens(text):
    try:
        r = requests.post(
            "http://127.0.0.1:8080/tokenize",
            json={"content": text},
            timeout=10
        )
        if r.status_code == 200:
            return len(r.json()["tokens"])
    except:
        pass
    return len(text) // 4

BLOCK_LINE = re.compile(r"^([-*+] |\d+[.)] |\|)")

def is_block_line(line):
    return BLOCK_LINE.match(line.strip()) is not None

def fix_markdown_spacing(text):
    lines = text.split("\n")
    fixed = []
    in_code = False
    previous = ""

    for line in lines:
        stripped = line.strip()
        needs_gap = False

        if stripped.startswith("```"):
            if not in_code and previous.strip():
                needs_gap = True
            in_code = not in_code
        elif not in_code and is_block_line(line) and previous.strip() and not is_block_line(previous):
            needs_gap = True

        if needs_gap:
            fixed.append("")
        fixed.append(line)
        previous = line

    return "\n".join(fixed)

class TopBar(QWidget):
    def __init__(self):
        super().__init__()

        self.menu_button = QPushButton("☰")
        self.title_label = QLabel("Local Qwen")
        self.projects_button = QPushButton("Projects")
        self.vision_button = QCheckBox("Enable Vision")
        self.vision_button.setChecked(False)
        self.vision_button.setToolTip("Loads the vision projector (~1.1 GB Vram). Restarts the model.")
        self.web_toggle = QCheckBox("Online mode")
        self.web_toggle.setChecked(False)
        self.theme_button = QPushButton("Dark Theme")
        self.theme_button.setIcon(QIcon("Icons-Pictures\\Dark-Theme.png"))

        self.initUI()

    def initUI(self):
        layout = QHBoxLayout()

        layout.addWidget(self.menu_button)
        layout.addWidget(self.title_label)
        layout.addWidget(self.projects_button)
        layout.addStretch()
        layout.addWidget(self.vision_button)
        layout.addWidget(self.web_toggle)
        layout.addWidget(self.theme_button)

        self.setLayout(layout)

class Sidebar(QWidget):
    chat_selected = pyqtSignal(str)
    chat_deleted = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self.chat_buttons = {}
        self.new_chat_button = QPushButton("New Chat")
        self.new_chat_button.setIcon(QIcon("Icons-Pictures\\new-chat.png"))

        # Scrollable chat logic
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_container = QWidget()
        
        self.chat_layout = QVBoxLayout()
        self.chat_layout.setContentsMargins(0, 0, 0, 0) 
        self.chat_layout.addStretch()

        self.chat_container.setLayout(self.chat_layout)
        self.chat_scroll.setWidget(self.chat_container)

        self.settings_button = QPushButton("Settings")
        self.settings_button.setIcon(QIcon("Icons-Pictures\\settings-icon.png"))

        # Sidebar animation start
        self.sidebar_open = True # sidebar will start open at 250 pixels
        self.setMinimumWidth(0)
        self.setMaximumWidth(250)

        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        layout.addWidget(self.new_chat_button)
        layout.addWidget(self.chat_scroll)
        layout.addWidget(self.settings_button)

        self.setLayout(layout)
    
    def add_chat(self, chat_id, title):
        row = QWidget()
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(4, 2, 4, 2)
        row_layout.setSpacing(4)
        chat_button = QPushButton(title)
        chat_button.setFixedWidth(160) # chat button takes more space
        chat_button.setToolTip(title)
        delete_button = QPushButton("❌")
        delete_button.setFixedWidth(30) # delete button takes less space

        row_layout.addWidget(chat_button)
        row_layout.addWidget(delete_button)

        row.setLayout(row_layout)

        self.chat_layout.insertWidget(self.chat_layout.count() - 1, row) # chats go top to bottom

        chat_button.clicked.connect(lambda: self.chat_selected.emit(chat_id))
        delete_button.clicked.connect(lambda: self.delete_chat(row, chat_id))

        self.chat_buttons[chat_id] = chat_button

    def rename_chat(self, chat_id, new_title):
        if chat_id in self.chat_buttons:
            self.chat_buttons[chat_id].setText(new_title)
            self.chat_buttons[chat_id].setToolTip(new_title)

    def delete_chat(self, row, chat_id):
        self.chat_layout.removeWidget(row)

        row.deleteLater()

        self.chat_buttons.pop(chat_id, None)
        self.chat_deleted.emit(chat_id)

class ChatArea(QWidget):
    STYLE = """
        body { font-family: "Segoe UI", "Segoe UI Emoji", sans-serif;
               font-size: 14px; }
        pre { font-family: "Cascadia Mono", Consolas, "Courier New", monospace;
              font-size: 13px; background-color: #f5f5f5; }
        code { font-family: "Cascadia Mono", Consolas, "Courier New", monospace;
               background-color: #f0f0f0; }
        table { border-collapse: collapse; border-style: solid; border-color: #cccccc; margin-top: 6px; margin-bottom: 6px; }
        th { background-color: #f0f0f0; font-weight: bold; }
        th, td { border-width: 1px; border-style: solid; border-color: #cccccc; padding: 6px 10px; }
        .role { font-weight: bold; }
        .user { color: #1a5fb4; }
        .assistant { color: #2a7a2a; }
        .system { color: #888888; font-style: italic; }
    """

    def __init__(self):
        super().__init__()

        self.chat_display = QTextBrowser()
        self.chat_display.setReadOnly(True)
        self.chat_display.setOpenExternalLinks(True)
        self.chat_display.document().setDefaultStyleSheet(self.STYLE)

        self.messages = []

        self.md = markdown.Markdown(
            extensions=["fenced_code", "codehilite", "tables", "sane_lists"],
            extension_configs={
                "codehilite": {"noclasses": True, "pygments_style": "friendly"}
            }
        )

        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        layout.addWidget(self.chat_display)
        
        self.setLayout(layout)

    def add_message(self, role, text):
        self.messages.append((role, text))
        self.render()

    def clear(self):
        self.messages = []
        self.render()

    def render(self):
        parts = []
        for role, text in self.messages:
            self.md.reset()
            body = self.md.convert(fix_markdown_spacing(text))
            body = body.replace("<table>", '<table border="1" cellspacing="0" cellpadding="6">')

            if role == "system":
                parts.append(f'<div class="system">{body}</div>')
                continue

            label = "You" if role == "user" else "Qwen"
            parts.append(
                f'<p class="role {role}">{label}:</p>{body}<hr>'
            )

        self.chat_display.setHtml("".join(parts))
        self.chat_display.moveCursor(QTextCursor.End)
        bar = self.chat_display.verticalScrollBar()
        bar.setValue(bar.maximum())

class PasteLineEdit(QLineEdit):
    image_pasted = pyqtSignal(QImage)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Paste): # covers CTRL + V and Shift + Insert. Text paste falls through to the default handler untouched.
            mime = QApplication.clipboard().mimeData()
            if mime.hasImage():
                image = QApplication.clipboard().image()
                if not image.isNull():
                    self.image_pasted.emit(image)
                    return
        super().keyPressEvent(event)

class InputBar(QWidget):
    def __init__(self):
        super().__init__()

        self.attach_button = QPushButton()
        self.attach_button.setIcon(QIcon("Icons-Pictures\\Attach.png"))
        self.attach_button.setToolTip("Attach files")
        self.input_box = PasteLineEdit()
        self.stop_button = QPushButton("⏹️ Stop")
        self.stop_button.setEnabled(False)
        self.send_button = QPushButton("▶️ Send")

        self.attachment_label = QLabel("")
        self.attachment_label.setVisible(False)
        self.clear_attachments_button = QPushButton("Clear")
        self.clear_attachments_button.setFixedWidth(60)
        self.clear_attachments_button.setVisible(False)

        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        attach_row = QHBoxLayout()
        attach_row.addWidget(self.attachment_label)
        attach_row.addStretch()
        attach_row.addWidget(self.clear_attachments_button)

        input_row = QHBoxLayout()
        input_row.addWidget(self.attach_button)
        input_row.addWidget(self.input_box)
        input_row.addWidget(self.stop_button)
        input_row.addWidget(self.send_button)

        layout.addLayout(attach_row)
        layout.addLayout(input_row)

        self.setLayout(layout)

class SettingsWindow(QDialog):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Settings")
        self.resize(400, 200)

        self.context_label = QLabel("Context Length")

        self.context_slider = QSlider(Qt.Horizontal)
        self.context_slider.setMinimum(0)
        self.context_slider.setMaximum(4)
        self.context_slider.setValue(1)

        self.context_value = [4096, 8192, 16384, 32768, 65536]
        self.value_label = QLabel("8192")

        self.advanced_label = QLabel("Advanced")

        # Model placement
        self.gpu_radio = QRadioButton("Auto (GPU + RAM/CPU)")
        self.hybrid_radio = QRadioButton("Hybrid (GPU + RAM)")
        self.cpu_radio = QRadioButton("CPU Only")

        self.model_group = QButtonGroup()

        self.model_group.addButton(self.gpu_radio)
        self.model_group.addButton(self.hybrid_radio)
        self.model_group.addButton(self.cpu_radio)
        self.gpu_radio.setChecked(True)

        # GPU Layers
        self.gpu_layers_label = QLabel("GPU Layers")
        self.gpu_layers_slider = QSlider(Qt.Horizontal)

        self.gpu_layers_slider.setMinimum(0)
        self.gpu_layers_slider.setMaximum(80)
        self.gpu_layers_slider.setValue(35)

        self.gpu_layers_value = QLabel("35")

        # Max tokens
        self.tokens_label = QLabel("Max Response Tokens")
        self.tokens_slider = QSlider(Qt.Horizontal)

        self.token_values = [256, 512, 1024, 2048, 4096, 8192]
        self.tokens_value_lbl = QLabel("2048")

        self.tokens_slider.setMinimum(0)
        self.tokens_slider.setMaximum(5)
        self.tokens_slider.setValue(3)

        self.save_button = QPushButton("Save settings")

        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        layout.addWidget(self.context_label)
        layout.addWidget(self.context_slider)
        layout.addWidget(self.value_label)

        layout.addWidget(self.advanced_label)
        layout.addWidget(self.gpu_radio)
        layout.addWidget(self.hybrid_radio)
        layout.addWidget(self.cpu_radio)

        layout.addWidget(self.gpu_layers_label)
        layout.addWidget(self.gpu_layers_slider)
        layout.addWidget(self.gpu_layers_value)

        layout.addWidget(self.tokens_label)
        layout.addWidget(self.tokens_slider)
        layout.addWidget(self.tokens_value_lbl)
        layout.addWidget(self.save_button, alignment=Qt.AlignRight)

        self.setLayout(layout)
        self.update_mode()

        # Signals/Events
        self.context_slider.valueChanged.connect(self.update_label)
        self.gpu_layers_slider.valueChanged.connect(self.update_gpu_layers)
        self.tokens_slider.valueChanged.connect(self.update_tokens)
        self.cpu_radio.toggled.connect(self.update_mode)
        self.gpu_radio.toggled.connect(self.update_mode)
        self.hybrid_radio.toggled.connect(self.update_mode)

    def update_label(self):
        value = self.context_value[self.context_slider.value()]
        self.value_label.setText(str(value))

    def update_gpu_layers(self):
        self.gpu_layers_value.setText(str(self.gpu_layers_slider.value()))

    def update_tokens(self):
        self.tokens_value_lbl.setText(str(self.token_values[self.tokens_slider.value()]))

    def update_mode(self):
        active = self.hybrid_radio.isChecked()
        self.gpu_layers_slider.setEnabled(active)
        self.gpu_layers_value.setEnabled(active)

    def load_settings(self, settings):
        # Context
        index = self.context_value.index(settings["context"])
        self.context_slider.setValue(index)

        # GPU Layers
        self.gpu_layers_slider.setValue(settings["gpu_layers"])

        # Max Tokens
        token_index = self.token_values.index(settings["max_tokens"])
        self.tokens_slider.setValue(token_index)
        self.update_mode()

        # Mode
        if settings["mode"] == "gpu":
            self.gpu_radio.setChecked(True)
        elif settings["mode"] == "hybrid":
            self.hybrid_radio.setChecked(True)
        else:
            self.cpu_radio.setChecked(True)

class ServerStartThread(QThread):
    ready = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, process):
        super().__init__()
        self.process = process

    def run(self):
        start = time.time()
        while time.time() - start < 300:
            if self.process.poll() is not None:
                self.failed.emit("llama-server process crashed or exited.")
                return
            try:
                r = requests.get("http://127.0.0.1:8080/health", timeout=2)
                if r.status_code == 200:
                    self.ready.emit()
                    return
            except:
                pass
            time.sleep(2)
        self.failed.emit("Timed out after 5 minutes.")

class InferenceThread(QThread):
    result_ready = pyqtSignal(str, str) # (answer, chat_id)

    def __init__(self, messages, max_tokens, chat_id):
        super().__init__()
        self.messages = messages
        self.max_tokens = max_tokens
        self.chat_id = chat_id
        self._abort = False

    def abort(self):
        self._abort = True

    def run(self):
        url = "http://127.0.0.1:8080/v1/chat/completions"

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            }
        ] + self.messages

        data = {
            "model": "Qwen",
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": 0.6,
            "top_p": 0.95,
            "chat_template_kwargs": {
                "enable_thinking": False
            },
            "stream": True
        }

        pieces = []
        response = None

        try:
            response = requests.post(
                url,
                json=data,
                timeout=900,
                stream=True
            )

            response.raise_for_status()
            response.encoding = "utf-8"

            for line in response.iter_lines(decode_unicode=True):
                if self._abort:
                    break
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                piece = choices[0].get("delta", {}).get("content")
                if piece:
                    pieces.append(piece)

            text = "".join(pieces)
            if self._abort:
                text = (text +"\n\n*[stopped]*") if text else "*[stopped]*"
            self.result_ready.emit(text, self.chat_id)

        except requests.exceptions.HTTPError:
            self.result_ready.emit(
                f"HTTP {response.status_code}\n\n{response.text}", self.chat_id
            )
        except Exception as e:
            if self._abort:
                self.result_ready.emit("".join(pieces) + "\n\n*[stopped]*", self.chat_id)
            else:
                self.result_ready.emit(f"{type(e).__name__}: {e}", self.chat_id)
        finally:
            if response is not None:
                response.close()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Local LLM")
        self.resize(1600, 900)
        self.setWindowIcon(QIcon("Icons-Pictures\\Qwen_logo.png"))

        self.top_bar = TopBar()
        self.sidebar = Sidebar()
        self.chat_area = ChatArea()
        self.input_bar = InputBar()
        self.settings_window = SettingsWindow()
        self.projects_window = ProjectsWindow(self) # Link to projects.py
        self.settings_window.save_button.clicked.connect(self.apply_settings)
        self.sidebar_animation = QPropertyAnimation(
            self.sidebar,
            b"maximumWidth"
        )
        self.sidebar_animation.setDuration(250)
    
        self.server_process = None
        self.attached_files = []
        self.project_root = r"F:\Python files\Qwen3.6_LocalLLM"
        self.mmproj_path = r".\LocalLLM\models\mmproj-F16.gguf"
        self.mmproj_available = os.path.exists(os.path.join(self.project_root, self.mmproj_path))
        self.vision_enabled = False
        self.searx = SearXClient()

        os.makedirs("chats", exist_ok=True)
        self.current_chat = None

        for filename in os.listdir("chats"):
            if filename.endswith(".json"):
                with open(f"chats/{filename}", encoding="utf8") as f:
                    data = json.load(f)
                chat_id = filename[:-5]

                self.sidebar.add_chat(chat_id, data["title"])

        self.model_settings = {
            "context": 8192,
            "gpu_layers": 35,
            "max_tokens": 2048,
            "mode": "gpu"
        }

        self.start_llama_server()
        self.initUI()

        self.dark_mode = True
        self.build_styles()
        self.apply_theme()

    # UI palette
    def build_styles(self):
        self.base_style = """
            QWidget {font-family: "Segoe UI"; font-size: 13px;}
            QPushButton {border-radius: 6px; padding: 6px 12px;}
            QLineEdit {border-radius: 6px; padding: 6px 8px;}
            QTextEdit, QTextBrowser, QListWidget {border-radius: 8px;}
            QCheckBox {spacing: 6px;}
    """
        # Themes
        self.dark_theme = f"""
            QWidget {{background-color: {BG_DARKMODE2}; color: {ASH_GRAY};}}
            QPushButton {{background-color: {MIDNIGHT_BLACK}; border: 1px solid {GUNMETAL_GRAY};}}
            QPushButton:hover {{background-color: {DEEP_PLUM}; }}
            QPushButton:pressed {{background-color: {DARK_ESPRESSO};}}
            QPushButton:disabled {{background-color: {DEEP_CHARCOAL}; color: {GUNMETAL_GRAY};}}
            QLineEdit, QTextEdit, QTextBrowser, QListWidget {{background-color: {MIDNIGHT_BLACK}; border: 1px solid {GUNMETAL_GRAY};}}
            QLineEdit:focus, QTextEdit:focus {{border: 1px solid {MUTED_ACCENT};}}
            QScrollArea {{border: 1px solid {GUNMETAL_GRAY};}}
    """
        self.light_theme = f"""
            QWidget {{background-color: {BG_LIGHTMODE}; color: {DEEP_BLACK};}}
            QPushButton {{background-color: {ASH_GRAY}; border: 1px solid {GUNMETAL_GRAY};}}
            QPushButton:hover {{background-color: {MUTED_ACCENT}; }}
            QPushButton:pressed {{background-color: {GUNMETAL_GRAY}; color: {ASH_GRAY};}}
            QPushButton:disabled {{background-color: {BG_LIGHTMODE}; color: {GUNMETAL_GRAY};}}
            QLineEdit, QTextEdit, QTextBrowser, QListWidget {{background-color: {ASH_GRAY}; border: 1px solid {GUNMETAL_GRAY};}}
            QLineEdit:focus, QTextEdit:focus {{border: 1px solid {DEEP_PLUM};}}
            QScrollArea {{border: 1px solid {GUNMETAL_GRAY};}}            
    """

    def apply_theme(self):
        if self.dark_mode:
            theme = self.dark_theme
            self.top_bar.theme_button.setText("Light Theme")
        else:
            theme = self.light_theme
            self.top_bar.theme_button.setText("Dark Theme")

        QApplication.instance().setStyleSheet(self.base_style + theme)

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.apply_theme()

    def start_searxng(self):
            docker = shutil.which("docker")
    
            if docker is None:
                self.chat_area.add_message(
                    "system", "Docker not installed. Online mode unavailable."
                )
                return False

            compose = os.path.join(
                os.getcwd(),
                "SearXNG"
            )
    
            result = subprocess.run(
                ["docker", "compose", "up", "-d"],
                cwd=compose,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                self.chat_area.add_message("system", f"SearXNG failed to start:\n{result.stderr}")
                return False
            return True

    def stop_searxng(self):
        compose = os.path.join(
            os.getcwd(),
            "SearXNG"
        )

        subprocess.run(
            ["docker", "compose", "down"],
            cwd=compose
        )

    def initUI(self):
        central_widget = QWidget()

        root_layout = QVBoxLayout()
        root_layout.addWidget(self.top_bar)

        middle_layout = QHBoxLayout()
        middle_layout.addWidget(self.sidebar, 20)
        middle_layout.addWidget(self.chat_area, 80)

        root_layout.addLayout(middle_layout)
        root_layout.addWidget(self.input_bar)

        central_widget.setLayout(root_layout)

        self.setCentralWidget(central_widget)

        # Signals/events
        self.top_bar.menu_button.clicked.connect(self.toggle_sidebar)
        self.sidebar.new_chat_button.clicked.connect(self.new_chat)
        self.sidebar.chat_selected.connect(self.load_chat)
        self.sidebar.chat_deleted.connect(self.delete_chat)
        self.sidebar.settings_button.clicked.connect(self.open_settings)
        self.input_bar.send_button.clicked.connect(self.send_message)
        self.input_bar.stop_button.clicked.connect(self.stop_generation)
        self.top_bar.web_toggle.toggled.connect(self.toggle_online_mode)
        self.input_bar.attach_button.clicked.connect(self.attach_files)
        self.input_bar.clear_attachments_button.clicked.connect(self.clear_attachements)
        self.input_bar.input_box.returnPressed.connect(self.send_message)
        self.top_bar.vision_button.toggled.connect(self.toggle_vision)
        self.input_bar.input_box.image_pasted.connect(self.attach_pasted_image)
        self.top_bar.projects_button.clicked.connect(self.projects_window.show)
        # Theme ----
        self.top_bar.theme_button.clicked.connect(self.toggle_theme)

        if not self.mmproj_available:
            self.top_bar.vision_button.setEnabled(False)
            self.top_bar.vision_button.setToolTip(f"mmproj file not found at {self.mmproj_path}")


    def toggle_sidebar(self):
        if self.sidebar.sidebar_open:
            self.sidebar_animation.setStartValue(250)
            self.sidebar_animation.setEndValue(0)
            self.sidebar.sidebar_open = False

        else:
            self.sidebar_animation.setStartValue(0)
            self.sidebar_animation.setEndValue(250)
            self.sidebar.sidebar_open = True

        self.sidebar_animation.start()

    def toggle_online_mode(self, enabled):
        if enabled:
            self.chat_area.add_message("system", "Starting Online Mode...")
            self.start_searxng()
            self.searx = SearXClient(base_url="http://127.0.0.1:8081")
        else:
            self.chat_area.add_message("system", "Online Mode disabled.")
            self.stop_searxng()

    def toggle_vision(self, enabled):
        thread = getattr(self, "inference_thread", None)
        if thread is not None and thread.isRunning():
            self.chat_area.add_message("system", "Can't switch vision while a response is generating.")
            self.top_bar.vision_button.blockSignals(True)
            self.top_bar.vision_button.setChecked(not enabled)
            self.top_bar.vision_button.blockSignals(False)
            return

        self.vision_enabled = enabled

        if enabled:
            self.chat_area.add_message("system", "Vision on. Restarting model - text generation will be slower.")
        else:
            dropped = [a for a in self.attached_files if a["kind"] == "image"]
            if dropped:
                self.attached_files = [a for a in self.attached_files if a["kind"] != "image"]
                self.update_attachment_label()
            self.chat_area.add_message("system", "Vision off. Restarting model...")

        self.restart_server()

    def restart_server(self):
        if self.server_process:
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
                self.server_process.wait()

        self.start_llama_server()
    
    def new_chat(self):
        existing_empty_chat = self.empty_chat()
        if existing_empty_chat is not None:
            self.current_chat = existing_empty_chat
            self.chat_area.clear()
            return
        
        chat_id = str(uuid.uuid4())

        data = {
            "title": "New Chat",
            "messages": []
        }

        with open(f"chats/{chat_id}.json", "w", encoding="utf8") as f:
            json.dump(data, f, indent=4)

        self.current_chat = chat_id
        self.sidebar.add_chat(chat_id, "New Chat")
        self.chat_area.clear()
    
    def empty_chat(self):
        for chat_id in self.sidebar.chat_buttons:
            if self.chat_is_empty(chat_id):
                return chat_id
        return None
    
    def send_message(self):
        self.last_web_sources = []
        prompt = self.input_bar.input_box.text()
        if not prompt and not self.attached_files:
            return
        if self.current_chat is None:
            self.new_chat()

        target_chat = self.current_chat # lock in the chat this request belongs to
        first_message = self.chat_is_empty(target_chat)

        attachments = self.attached_files
        self.attached_files = []
        self.update_attachment_label()

        text_files = [a for a in attachments if a["kind"] == "text"]
        image_files = [a for a in attachments if a["kind"] == "image"]

        # what actually gets saved and sent as text
        stored_prompt = prompt
        if text_files:
            blocks = [
                f"--- Attached file: {a['name']} ---\n{a['text']}"
                for a in text_files
            ]
            stored_prompt = (
                "Attached files: \n\n" + "\n\n".join(blocks)
                + f"\n\n---\n\n{prompt}"
            )
        if image_files:
            names = ", ".join(a["name"] for a in image_files)
            stored_prompt = f"[Attached images: {names}]\n\n{stored_prompt}"

        display = prompt or "(no message)"
        if attachments:
            display += "\n\n`attached: " + ", ".join(a["name"] for a in attachments) + "`"
        self.chat_area.add_message("user", display)

        self.append_message(target_chat, "user", stored_prompt)

        if first_message:
            title_source = prompt or attachments[0]["name"]
            self.rename_chat(target_chat, self.make_title(title_source))

        self.input_bar.input_box.clear()
        self.input_bar.send_button.setEnabled(False)  # disable while generating
        self.input_bar.stop_button.setEnabled(True)
        self.sidebar.setEnabled(False) # block switching/new-chat mid-generation

        messages = self.get_chat_messages(target_chat, len(image_files) * IMAGE_TOKEN_COST)

        # swap the last user message to multimodal content when images are attached
        if image_files and messages:
            content = [{"type": "text", "text": messages[-1]["content"]}]
            for a in image_files:
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{a['media_type']};base64,{a['data']}"
                    }
                })
            messages[-1] = {"role": "user", "content": content}

        if self.top_bar.web_toggle.isChecked():

            web_context = self.build_web_context(prompt, target_chat)

            if web_context:
                messages.insert(
                    0,
                    {
                        "role": "system",
                        "content": web_context
                    }
                )

        self.inference_thread = InferenceThread(messages, self.model_settings["max_tokens"], target_chat)
        self.inference_thread.result_ready.connect(self.on_response)
        self.inference_thread.start()

    def stop_generation(self):
        thread = getattr(self, "inference_thread", None)
        if thread is not None and thread.isRunning():
            thread.abort()
            self.input_bar.stop_button.setEnabled(False)

    def append_message(self, chat_id, role, text):
        filename = f"chats/{chat_id}.json"
        with open(filename, "r", encoding="utf8") as f:
            data = json.load(f)

        data["messages"].append({
            "role": role,
            "content": text,
            "tokens": count_tokens(text) # compute once, reuse forever
        })
        with open(filename, "w", encoding="utf8") as f:
            json.dump(data, f, indent=4)
    
    def load_chat(self, chat_id):
        self.current_chat = chat_id

        self.chat_area.clear()

        with open(f"chats/{chat_id}.json", encoding="utf8") as f:
            data = json.load(f)

        for message in data["messages"]:
            self.chat_area.add_message(message["role"], message["content"])

    def chat_is_empty(self, chat_id):
        filename = f"chats/{chat_id}.json"
        if not os.path.exists(filename):
            return False
        with open(filename, "r", encoding="utf8") as f:
            data = json.load(f)
        return len(data["messages"]) == 0
    
    def make_title(self, prompt, max_length=40):
        title = " ".join(prompt.split()) # collapses newlines/extra spaces
        if len(title) > max_length:
            title = title[:max_length].rsplit(" ", 1)[0] + "…"
        return title
    
    def rename_chat(self, chat_id, new_title):
        filename = f"chats/{chat_id}.json"
        with open(filename, "r", encoding="utf8") as f:
            data = json.load(f)
        data["title"] = new_title
        with open(filename, "w", encoding="utf8") as f:
            json.dump(data, f, indent=4)

        self.sidebar.rename_chat(chat_id, new_title)

    def get_chat_messages(self, chat_id, reserve=0):
        filename = f"chats/{chat_id}.json"

        with open(filename, "r", encoding="utf8") as f:
            data = json.load(f)

        return self.message_budget(data["messages"], reserve)

    def build_web_context(self, query, chat_id):
        search_query = query
        try:
            with open(f"chats/{chat_id}.json", "r", encoding="utf8") as f:
                title = json.load(f).get("title", "")
            if title and title.lower() not in query.lower():
                search_query = f"{title} {query}"
        except Exception:
            pass

        try:
            results = self.searx.search(search_query)
        except Exception as e:
            self.chat_area.add_message("system", f"Web search failed - {type(e).__name__}: {e}")
            self.last_web_sources = []
            return ""
        
        self.last_web_sources = results

        context = "Internet search results:\n\n"
        for result in results:
            context += f"Title: {result['title']}\n"
            context += f"URL: {result['url']}\n"
            context += f"Snippet: {result['content']}\n\n"
        context += (
            "If these results don't actually address the question, say so directly "
            "instead of guessing or inventing an explanation. \n"
            "Base your answer on these results. If they do not cover the question, "
            "say that you could not find current information rather than stating "
            "that something does not exist. Distinguish professional critic reviews "
            "from player or user reviews, and say which ones the results cover.\n"
        )

        return context
    
    def message_budget(self, messages, reserve=0):
        context = self.model_settings["context"]
        max_tokens = self.model_settings["max_tokens"]

        if not hasattr(self, "_system_tokens_cache"):
            self._system_tokens_cache = count_tokens(SYSTEM_PROMPT)
        system_tokens = self._system_tokens_cache
        safety_margin = 200

        budget = context - max_tokens - system_tokens - safety_margin - reserve
        if budget <= 0 or not messages:
            return messages[-1:] if messages else []
        
        trimmed = []
        running_total = 0

        for message in reversed(messages):
            msg_tokens = message.get("tokens")
            if msg_tokens is None: # older chats saved before this change
                msg_tokens = count_tokens(message["content"])
            if running_total + msg_tokens > budget:
                break
            trimmed.insert(0, message)
            running_total += msg_tokens

        return trimmed if trimmed else messages[-1:]

    def delete_chat(self, chat_id):
        filename = f"chats/{chat_id}.json"

        if os.path.exists(filename):
            os.remove(filename)

        if self.current_chat == chat_id:
            self.current_chat = None
            self.chat_area.clear()

    def on_response(self, answer, chat_id):
        self.append_message(chat_id, "assistant", answer) # always saves to the right chat
        if self.current_chat == chat_id:
            self.chat_area.add_message("assistant", answer)
            if getattr(self, "last_web_sources", None):
                lines = "\n".join(
                    f"- [{r['title']}]({r['url']})" for r in self.last_web_sources
                )
                self.chat_area.add_message("system", "Sources:\n" + lines)

        self.input_bar.send_button.setEnabled(True)  # re-enable when done
        self.input_bar.stop_button.setEnabled(False)
        self.sidebar.setEnabled(True)

    def attach_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Attach files", "",
            "All supported (*.txt *.md *.py *.js *.json *.csv *.yaml *.yml *.html *.css "
            "*.xml *.log *.pdf *.docx *.xlsx *.png *.jpg *.jpeg *.webp *.gif *.bmp);;"
            "Documents and code (*.txt *.md *.py *.js *.json *.csv *.yaml *.yml "
            "*.html *.css *.xml *.log *.pdf *.docx *.xlsx);;"
            "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp);;"
            "All files (*)"
        )
        if not paths:
            return

        for path in paths:
            try:
                attachment = load_file(path)
            except UnsupportedFile as e:
                self.chat_area.add_message("system", str(e))
                continue
            except Exception as e:
                self.chat_area.add_message(
                    "system",
                    f"Could not read {os.path.basename(path)} - {type(e).__name__}: {e}"
                )
                continue

            if attachment["kind"] == "image" and not self.vision_active():
                if not self.mmproj_available:
                    reason = f"mmproj file not found at {self.mmproj_path}"
                else:
                    reason = "vision is off - tick 'Enable Vision' in the top bar."
                self.chat_area.add_message("system", f"{attachment['name']} skipped: {reason}.")
                continue
            self.attached_files.append(attachment)

        self.update_attachment_label()

    def attach_pasted_image(self, image):
        if not self.vision_active():
            if not self.mmproj_available:
                reason = f"mmproj file not found at {self.mmproj_path}"
            else:
                reason = "vision is off - tick 'Enable Vision' in the top bar"
            self.chat_area.add_message("system", f"Pasted image ignored: {reason}.")
            return

        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        raw = bytes(buffer.data())
        buffer.close()

        name = f"pasted-{time.strftime('%H%M%S')}.png"
        try:
            self.attached_files.append(load_image_bytes(raw, name))
        except Exception as e:
            self.chat_area.add_message("system", f"Could not read pasted image - {type(e).__name__}: {e}")
            return

        self.update_attachment_label()

    def clear_attachements(self):
        self.attached_files = []
        self.update_attachment_label()

    def update_attachment_label(self):
        if not self.attached_files:
            self.input_bar.attachment_label.setVisible(False)
            self.input_bar.clear_attachments_button.setVisible(False)
            return

        names = []
        for a in self.attached_files:
            if a["kind"] == "text":
                names.append(f"{a['name']} (~{count_tokens(a['text'])} tok)")
            else:
                names.append(f"{a['name']} (image)")

        self.input_bar.attachment_label.setText("Attached: " + ", ".join(names))
        self.input_bar.attachment_label.setVisible(True)
        self.input_bar.clear_attachments_button.setVisible(True)

    def start_llama_server(self):
        if self.model_settings["mode"] == "gpu":
            ngl = 999
 
        elif self.model_settings["mode"] == "hybrid":
            ngl = self.model_settings["gpu_layers"]
 
        else:
            ngl = 0

        args = [
            r".\LocalLLM\backend_13.3\llama-server.exe",
            "-m", r".\LocalLLM\models\Qwen3.6-27B-UD-IQ3_XXS.gguf",
        ]
        args += [
            "-c", str(self.model_settings["context"]),
            "--parallel", "1",
            "--threads", "8",
            "--flash-attn", "on",
            "--jinja",
        ]
        if self.vision_active():
            args += ["--mmproj", self.mmproj_path, "--image-min-tokens", "1024"]

        if self.model_settings["mode"] != "gpu":
            args += ["-ngl", str(ngl)]

        self.server_process = subprocess.Popen(args, cwd=self.project_root)

        #stdout=subprocess.DEVNULL, # subprocess terminal output
        #stderr=subprocess.DEVNULL
        self.wait_for_server()

    def vision_active(self):
        return self.mmproj_available and self.vision_enabled

    def wait_for_server(self):
        self.chat_area.add_message("system", "Loading model, please wait...")
        self.input_bar.send_button.setEnabled(False) # disable send while loading
        self.top_bar.vision_button.setEnabled(False)

        self.server_thread = ServerStartThread(self.server_process)
        self.server_thread.ready.connect(self.on_server_ready)
        self.server_thread.failed.connect(self.on_server_failed)
        self.server_thread.start()

    def on_server_ready(self):
        self.chat_area.add_message("system", "Model ready.\n")
        self.input_bar.send_button.setEnabled(True) # re-enable send
        self.top_bar.vision_button.setEnabled(self.mmproj_available)

    def on_server_failed(self, reason):
        self.chat_area.add_message("system", f"Model failed to load in time - {reason}")
        self.top_bar.vision_button.setEnabled(self.mmproj_available)

    def open_settings(self):
        self.settings_window.load_settings(self.model_settings)
        self.settings_window.show()

    def apply_settings(self):
        thread = getattr(self, "inference_thread", None)
        if thread is not None and thread.isRunning():
            self.chat_area.add_message(
                "system", "Can't change model settings while a response is generating."
            )
            return
        old = dict(self.model_settings)

        self.model_settings["context"] = self.settings_window.context_value[self.settings_window.context_slider.value()]
        self.model_settings["gpu_layers"] = self.settings_window.gpu_layers_slider.value()
        self.model_settings["max_tokens"] = self.settings_window.token_values[self.settings_window.tokens_slider.value()]

        if self.settings_window.cpu_radio.isChecked():
            self.model_settings["mode"] = "cpu"

        elif self.settings_window.hybrid_radio.isChecked():
            self.model_settings["mode"] = "hybrid"

        else:
            self.model_settings["mode"] = "gpu"

        self.settings_window.hide()

        keys = ["context", "mode"]
        if self.model_settings["mode"] == "hybrid":
            keys.append("gpu_layers")

        if all(old[k] == self.model_settings[k] for k in keys):
            self.chat_area.add_message("system", "Settings saved.")
            return

        self.chat_area.add_message("system", "Restarting model...")
        self.restart_server()

    def new_chat_area(self): # method to open ChatArea() in projects_window.py
        return ChatArea()

    def new_input_bar(self): # method to open InputBar() in projects_window.py
        return InputBar()

    def new_inference_thread(self, messages, chat_id): # method to open InferenceThread in projects_window.py
        return InferenceThread(messages, self.model_settings["max_tokens"], chat_id)

    def token_count(self, text):
        return count_tokens(text) # method to run count_tokens in projects_window.py

    def rewrite_search_query(self, history, prompt):
        recent = history[-5:-1] # the turns before the current message
        lines = []
        for message in recent:
            text = message["content"][:300]
            lines.append(f"{message['role']}: {text}")
        conversation = "\n".join(lines)

        instruction = (
            "Rewrite the user's latest message as a short standalone web search query "
            "(max 10 words). Include the specific names it refers to. Describe only the "
            "topic - do not include the user's claims, opinions or expected answer. "
            "Output only the query, nothing else."
        )
        body = {
            "model": "Qwen",
            "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": f"Conversation:\n{conversation}\n\nLatest message: {prompt}"}
            ],
            "max_tokens": 30,
            "temperature": 0,
            "chat_template_kwargs": {"enable_thinking": False}
        }

        try:
            r = requests.post("http://127.0.0.1:8080/v1/chat/completions", json=body, timeout=60)
            r.raise_for_status()
            query = r.json()["choices"][0]["message"]["content"].strip().strip('"')
        except Exception:
            return prompt

        if not query:
            return prompt
        return query

    def closeEvent(self, event): # Kill server when app window is closed (closeEvent default Qt method)
        thread = getattr(self, "inference_thread", None)
        if thread is not None and thread.isRunning():
            thread.abort()
            thread.wait(3000)

        if self.server_process:
            self.server_process.terminate()

        if self.top_bar.web_toggle.isChecked():
            self.stop_searxng()

        event.accept()

app = QApplication(sys.argv)

window = MainWindow()
window.show()

sys.exit(app.exec_())