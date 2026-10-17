import json
import os
import shutil
import uuid
from PyQt5.QtWidgets import (QDialog, QListWidget, QListWidgetItem, QPushButton, QLabel, 
                             QVBoxLayout, QHBoxLayout, QMessageBox, QInputDialog, QWhatsThis)
from PyQt5.QtCore import Qt, QEvent, QTimer

PROJECTS_DIR = "projects"

PROJECTS_HELP = """
    <b>Projects</b><br>
    Each project is its own conversation with its own reference material.
    <ul>
    <li><b>Create Project</b> - name a new project. It opens straight away.</li>
    <li><b>Open</b> or double-click - opens the project's chat window.</li>
    <li><b>Rename / Delete</b> - select a project first. Delete permanently removes its conversation, instructions and images.</li>
    </ul>
    <b>Inside a project</b>
    <ul>
    <li><b>Instructions</b> - notes and images the model sees with every message in that project.</li>
    <li>Each reference image costs about 1100 tokens per message, so keep them few and put most material in notes.</li>
    <li>Images need <b>Enable Vision</b>. Online mode is switched on from the main window.</li>
    </ul>
"""

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")

def project_dir(project_id):
    return os.path.join(PROJECTS_DIR, project_id)

def json_path(project_id):
    return os.path.join(project_dir(project_id), "project.json")

def files_dir(project_id):
    return os.path.join(project_dir(project_id), "files")

def load_project(project_id):
    path = json_path(project_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf8") as f:
            return json.load(f)
    except Exception:
        return None

def save_project(project_id, data):
    os.makedirs(project_dir(project_id), exist_ok=True)
    with open(json_path(project_id), "w", encoding="utf8") as f:
        json.dump(data, f, indent=4)

def create_project(name):
    project_id = str(uuid.uuid4())
    save_project(project_id, {
        "name": name,
        "instructions": "",
        "messages": []
    })
    os.makedirs(files_dir(project_id), exist_ok=True)
    return project_id

def list_projects():
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    rows = []
    for project_id in os.listdir(PROJECTS_DIR):
        data = load_project(project_id)
        if data:
            rows.append((
                project_id,
                data.get("name", "Untitled"),
                len(data.get("messages", []))
            ))
    return sorted(rows, key=lambda row: row[1].lower())

def rename_project(project_id, name):
    data = load_project(project_id)
    if data is None:
        return
    data["name"] = name
    save_project(project_id, data)

def delete_project(project_id):
    folder = project_dir(project_id)
    if os.path.isdir(folder):
        shutil.rmtree(folder)

def append_message(project_id, role, text, tokens):
    data = load_project(project_id)
    if data is None:
        return
    data["messages"].append({
        "role": role,
        "content": text,
        "tokens": tokens
    })
    save_project(project_id, data)

# Storage methods for instructions dialog
def save_instructions(project_id, text):
    data = load_project(project_id)
    if data is None:
        return
    data["instructions"] = text
    save_project(project_id, data)

def image_paths(project_id):
    folder = files_dir(project_id)
    if not os.path.isdir(folder):
        return []
    paths = []
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith(IMAGE_EXTS):
            paths.append(os.path.join(folder, name))
    return paths

def unique_target(project_id, name): # return a path in files / that does not exist yet.
    os.makedirs(files_dir(project_id), exist_ok=True)
    target = os.path.join(files_dir(project_id), name)
    stem, ext = os.path.splitext(name)
    counter = 1
    while os.path.exists(target):
        target = os.path.join(files_dir(project_id), f"{stem}_{counter}{ext}")
        counter += 1
    return target

def add_image_file(project_id, source_path):
    target = unique_target(project_id, os.path.basename(source_path))
    shutil.copy2(source_path, target)
    return target

def add_image_bytes(project_id, raw, name):
    target = unique_target(project_id, name)
    with open(target, "wb") as f:
        f.write(raw)
    return target

def remove_image(path):
    try:
        os.remove(path)
        return True
    except OSError:
        return False

class ProjectsWindow(QDialog):
    def __init__(self, host):
        super().__init__(host)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, True)
        self.host = host
        self.setWindowTitle("Projects")
        self.resize(900, 620)

        self.open_windows = {}

        self.title_label = QLabel("Personal Projects")
        self.create_button = QPushButton("Create Project")
        self.project_list = QListWidget()
        self.rename_button = QPushButton("Rename")
        self.delete_button = QPushButton("Delete")
        self.open_button = QPushButton("Open")

        self.initUI()
        self.refresh()

    def initUI(self):
        header = QHBoxLayout()
        header.addWidget(self.title_label)
        header.addStretch()
        header.addWidget(self.create_button)

        footer = QHBoxLayout()
        footer.addStretch()
        footer.addWidget(self.rename_button)
        footer.addWidget(self.delete_button)
        footer.addWidget(self.open_button)

        layout = QVBoxLayout()
        layout.addLayout(header)
        layout.addWidget(self.project_list)
        layout.addLayout(footer)

        self.setLayout(layout)

        # Signals / connectors
        self.create_button.clicked.connect(self.create)
        self.rename_button.clicked.connect(self.rename_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        self.project_list.itemDoubleClicked.connect(self.open_selected)
        self.open_button.clicked.connect(self.open_selected)

    def refresh(self, select_id=None):
        self.project_list.clear()
        for project_id, name, count in list_projects():
            suffix = "empty" if count == 0 else f"{count} messages"
            item = QListWidgetItem(f"{name} - {suffix}")
            item.setData(Qt.UserRole, project_id) # Syntax: role, value
            self.project_list.addItem(item)
            if project_id == select_id:
                self.project_list.setCurrentItem(item)

    def selected_id(self):
        item = self.project_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def create(self):
        name, ok = QInputDialog.getText(self, "Create Project", "Project name:") # Syntax (parent, title, label)
        if not ok:
            return
        project_id = create_project(name.strip() or "Untitled")
        self.refresh(select_id=project_id)

    def rename_selected(self):
        project_id = self.selected_id()
        if not project_id:
            QMessageBox.information(self, "Rename Project", "Select a project first.")
            return
        data = load_project(project_id)
        if data is None:
            QMessageBox.warning(self, "Rename Project", "That project could not be read.")
            self.refresh()
            return

        name, ok = QInputDialog.getText(self, "Rename Project", "Project name:", text=data["name"])
        if not ok:
            return
        rename_project(project_id, name.strip() or "Untitled")
        self.refresh(select_id=project_id)

    def delete_selected(self):
        project_id = self.selected_id()
        if not project_id:
            QMessageBox.information(self, "Delete project", "Select a project first.")
            self.refresh()
            return
        data = load_project(project_id) or {}
        confirm = QMessageBox.question( # Syntax: (parent, title, text, buttons, defaultButton)
            self, "Delete project",
            f"Delete '{data.get('name', 'this project')}' and its whole conversation?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No # second QMessageBox is the defaultButton (fallback)
        )
        if confirm != QMessageBox.Yes:
            return
        delete_project(project_id)
        self.refresh()

    def open_selected(self):
        project_id = self.selected_id()
        if not project_id:
            QMessageBox.information(self, "Open Project", "Select a project first.")
            return
        self.open_project(project_id)

    def open_project(self, project_id):
        from projects_window import ProjectChatWindow

        window = self.open_windows.get(project_id)
        if window is None:
            window = ProjectChatWindow(self.host, project_id)
            self.open_windows[project_id] = window

        window.show()
        window.raise_()
        window.activateWindow()

    # Making the QDialog's question mark at the top actually provide instructions
    def event(self, event):
        if event.type() == QEvent.EnterWhatsThisMode and self.isActiveWindow():
            QWhatsThis.leaveWhatsThisMode()
            QTimer.singleShot(0, self.show_help)
            return True
        return super().event(event)

    def show_help(self):
        QMessageBox.information(self, "How to use Projects", PROJECTS_HELP)
