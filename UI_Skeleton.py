import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QPushButton, QTextEdit,
                             QLineEdit, QLabel, QVBoxLayout, QHBoxLayout)

class TopBar(QWidget):
    def __init__(self):
        super().__init__()

        self.menu_button = QPushButton("☰")
        self.title_label = QLabel("Local Qwen")
        self.theme_button = QPushButton("Dark Theme")

        self.initUI()

    def initUI(self):
        layout = QHBoxLayout()

        layout.addWidget(self.menu_button)
        layout.addWidget(self.title_label)
        layout.addStretch()
        layout.addWidget(self.theme_button)

        self.setLayout(layout)

class Sidebar(QWidget):
    def __init__(self):
        super().__init__()

        self.new_chat_button = QPushButton("+ New Chat")
        self.chat1 = QPushButton("Chat 1")
        self.chat2 = QPushButton("Chat 2")
        self.chat3 = QPushButton("Chat 3")

        self.settings_button = QPushButton("Settings")

        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        layout.addWidget(self.new_chat_button)

        layout.addWidget(self.chat1)
        layout.addWidget(self.chat2)
        layout.addWidget(self.chat3)
        layout.addStretch()
        layout.addWidget(self.settings_button)

        self.setLayout(layout)

class ChatArea(QWidget):
    def __init__(self):
        super().__init__()

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)

        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        layout.addWidget(self.chat_display)
        
        self.setLayout(layout)

class InputBar(QWidget):
    def __init__(self):
        super().__init__()

        self.attach_button = QPushButton("📎")
        self.input_box = QLineEdit()
        self.stop_button = QPushButton("⏹️ Stop")
        self.send_button = QPushButton("▶️ Send")

        self.initUI()

    def initUI(self):
        layout = QHBoxLayout()

        layout.addWidget(self.attach_button)
        layout.addWidget(self.input_box)
        layout.addWidget(self.stop_button)
        layout.addWidget(self.send_button)

        self.setLayout(layout)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Local LLM")
        self.resize(1600, 900)

        self.top_bar = TopBar()
        self.sidebar = Sidebar()
        self.chat_area = ChatArea()
        self.input_bar = InputBar()

        self.initUI()

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

app = QApplication(sys.argv)

window = MainWindow()
window.show()

sys.exit(app.exec_())