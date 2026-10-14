from PyQt5.QtWidgets import (QMainWindow, QWidget, QPushButton, 
                             QLabel, QCheckBox, QVBoxLayout, QHBoxLayout, QApplication, QDialog, QTextEdit,
                             QListWidget, QListWidgetItem, QFileDialog, QMessageBox)
from projects import (load_project, save_instructions, image_paths, add_image_file, add_image_bytes,
                      remove_image, append_message)
from PyQt5.QtCore import Qt, QSize, QBuffer, QIODevice
from PyQt5.QtGui import QIcon, QPixmap
import os
import time
from file_loader import load_file, load_image_bytes, UnsupportedFile

IMAGE_TOKEN_COST = 1100

class InstructionsWindow(QDialog):
    def __init__(self, host, project_id):
        super().__init__(host)
        self.host = host
        self.project_id = project_id

        self.setWindowTitle("Instructions")
        self.resize(760, 640)

        self.name_label = QLabel()
        self.notes_label = QLabel("Instructions / Reference notes")
        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText("Anything written here is sent with every message in this project.")

        self.image_label = QLabel("Reference images")
        self.image_list = QListWidget()
        self.image_list.setViewMode(QListWidget.IconMode)
        self.image_list.setIconSize(QSize(120, 90))
        self.image_list.setResizeMode(QListWidget.Adjust)
        self.image_list.setFixedHeight(160)

        self.add_images_button = QPushButton("Add images")
        self.paste_image_button = QPushButton("Paste image")
        self.remove_image_button = QPushButton("Remove selected")

        self.cost_label = QLabel("")
        self.save_button = QPushButton("Save")

        self.initUI()
        self.load_data()

    def initUI(self):
        image_buttons = QHBoxLayout()
        image_buttons.addWidget(self.add_images_button)
        image_buttons.addWidget(self.paste_image_button)
        image_buttons.addWidget(self.remove_image_button)
        image_buttons.addStretch()

        footer = QHBoxLayout()
        footer.addWidget(self.cost_label)
        footer.addStretch()
        footer.addWidget(self.save_button)

        layout = QVBoxLayout()
        layout.addWidget(self.name_label)
        layout.addWidget(self.notes_label)
        layout.addWidget(self.notes_edit)
        layout.addWidget(self.image_label)
        layout.addWidget(self.image_list)
        layout.addLayout(image_buttons)
        layout.addLayout(footer)

        self.setLayout(layout)

        # Signals / connectors
        self.add_images_button.clicked.connect(self.add_images)
        self.paste_image_button.clicked.connect(self.paste_image)
        self.remove_image_button.clicked.connect(self.remove_selected_image)
        self.save_button.clicked.connect(self.save)
        self.notes_edit.textChanged.connect(self.update_cost)

    def load_data(self):
        data = load_project(self.project_id) or {}
        self.name_label.setText(data.get("name", "Untitled"))
        self.notes_edit.setPlainText(data.get("instructions", ""))
        self.refresh_images()

    def refresh_images(self):
        self.image_list.clear()
        for path in image_paths(self.project_id):
            item = QListWidgetItem(os.path.basename(path))
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(120, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                item.setIcon(QIcon(scaled))
            item.setData(Qt.UserRole, path)
            self.image_list.addItem(item)
        self.update_cost()

    def update_cost(self):
        note_tokens = len(self.notes_edit.toPlainText()) // 4
        image_count = self.image_list.count()
        total = note_tokens + image_count * IMAGE_TOKEN_COST
        text = (
            f"~{total} tokens added to every message "
            f"({note_tokens} notes + {image_count} image(s))"
        )
        vision_off = self.host is not None and not self.host.vision_active()
        if image_count > 0 and vision_off:
            text += " - VISION IS OFF, images will not be sent"
        self.cost_label.setText(text)

    def add_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add reference images", "",
            "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp)"
        )
        for path in paths:
            add_image_file(self.project_id, path)
        self.refresh_images()

    def paste_image(self):
        image = QApplication.clipboard().image()
        if image.isNull():
            QMessageBox.information(self, "Paste image", "No image on the clipboard.")
            return
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        raw = bytes(buffer.data())
        buffer.close()

        add_image_bytes(self.project_id, raw, "pasted.png")
        self.refresh_images()

    def remove_selected_image(self):
        item = self.image_list.currentItem()
        if item is None:
            QMessageBox.information(self, "Remove image", "Select an image first.")
            return

        path = item.data(Qt.UserRole)
        confirm = QMessageBox.question(
            self, "Remove image",
            f"Permanently delete {os.path.basename(path)} from this project?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        remove_image(path)
        self.refresh_images()

    def save(self):
        save_instructions(self.project_id, self.notes_edit.toPlainText())

    def closeEvent(self, event):
        self.save()
        event.accept()

class ProjectChatWindow(QMainWindow):
    def __init__(self, host, project_id):
        super().__init__(host)
        self.host = host
        self.project_id = project_id

        if host is None: # just for testing purposes
            from PyQt5.QtWidgets import QTextBrowser, QLineEdit
            self.chat_area = QTextBrowser()
            self.input_bar = QLineEdit()
        else:
            self.chat_area = host.new_chat_area()
            self.input_bar = host.new_input_bar()

        self.resize(1080, 700)

        self.attached_files = []
        self.inference_thread = None
        self.last_web_sources = []

        self.name_label = QLabel()
        self.instructions_button = QPushButton("Instructions")
        self.vision_toggle = QCheckBox("Enable Vision")
        self.online_label = QLabel("Online mode: OFF")

        self.initUI()
        self.refresh_name()
        self.sync_from_host()
        if self.host is not None:
            self.load_history()

    def initUI(self):
        top_bar = QWidget()
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.name_label)
        top_layout.addStretch()
        top_layout.addWidget(self.instructions_button)
        top_layout.addWidget(self.vision_toggle)
        top_layout.addWidget(self.online_label)
        top_bar.setLayout(top_layout)

        central_widget = QWidget()
        root_layout = QVBoxLayout()
        root_layout.addWidget(top_bar)
        root_layout.addWidget(self.chat_area)
        root_layout.addWidget(self.input_bar)
        central_widget.setLayout(root_layout)

        self.setCentralWidget(central_widget)

        # Signals / connectors
        self.instructions_button.clicked.connect(self.open_instructions)
        self.vision_toggle.toggled.connect(self.on_vision_toggled)

        if self.host is not None:
            self.host.top_bar.vision_button.toggled.connect(self.sync_from_host)
            self.host.top_bar.web_toggle.toggled.connect(self.sync_from_host)

        self.input_bar.attach_button.clicked.connect(self.attach_files)
        self.input_bar.clear_attachments_button.clicked.connect(self.clear_attachments)
        self.input_bar.input_box.image_pasted.connect(self.attach_pasted_image)
        self.input_bar.send_button.clicked.connect(self.send_message)
        self.input_bar.stop_button.clicked.connect(self.stop_generation)
        self.input_bar.input_box.returnPressed.connect(self.send_message)

    def refresh_name(self):
        data = load_project(self.project_id) if self.project_id else {}
        name = (data or {}).get("name", "Untitled")
        self.setWindowTitle(f"Project - {name}")
        self.name_label.setText(name)

    def open_instructions(self):
        window = InstructionsWindow(self.host, self.project_id)
        window.exec_()
        self.refresh_name()

    def sync_from_host(self):
        if self.host is None:
            return

        online = self.host.top_bar.web_toggle.isChecked()
        self.online_label.setText(f"Online mode: {'ON' if online else 'OFF'}")

        self.vision_toggle.blockSignals(True)
        self.vision_toggle.setChecked(self.host.vision_enabled)
        self.vision_toggle.setEnabled(self.host.mmproj_available)
        self.vision_toggle.blockSignals(False)

    def on_vision_toggled(self, enabled):
        if self.host is None:
            return
        self.host.top_bar.vision_button.setChecked(enabled)

    def load_history(self):
        self.chat_area.clear()
        data = load_project(self.project_id) or {}
        for message in data.get("messages", []):
            self.chat_area.add_message(message["role"], message["content"])

    # Attachments
    def attach_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Attach files", "",
            "All supported (*.txt *.md *.py *.js *.json *.csv *.yaml *.yml *.html *.css "
            "*.xml *.log *.pdf *.docx *.xlsx *.png *.jpg *.jpeg *.webp *.gif *.bmp);;"
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
            if attachment["kind"] == "image" and not self.host.vision_active():
                self.chat_area.add_message(
                    "system",
                    f"{attachment['name']} skipped: vision is off - tick 'Enable Vision' above."
                )
                continue
            self.attached_files.append(attachment)

        self.update_attachment_label()

    def attach_pasted_image(self, image):
        if not self.host.vision_active():
            self.chat_area.add_message(
                "system", "Pasted image ignored: VISION is off - tick 'Enable Vision' above."
            )
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
            self.chat_area.add_message(
                "system", f"Could not read pasted image - {type(e).__name__}: {e}"
            )
            return

        self.update_attachment_label()

    def clear_attachments(self):
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
                names.append(f"{a['name']} (~{self.host.token_count(a['text'])} tok)")
            else:
                names.append(f"{a['name']} (image)")

        self.input_bar.attachment_label.setText("Attached: " + ", ".join(names))
        self.input_bar.attachment_label.setVisible(True)
        self.input_bar.clear_attachments_button.setVisible(True)

    # Web context: Send & Receive
    def build_web_context(self, query):
        try:
            results = self.host.searx.search(query)
        except Exception as e:
            self.chat_area.add_message(
                "system", f"Web search failed - {type(e).__name__}: {e}"
            )
            self.last_web_sources = []
            return ""

        if not results:
            reason = "no results"
            failed = self.host.searx.last_unresponsive
            if failed:
                names = []
                for engine in failed:
                    names.append(f"{engine[0]} ({engine[1]})")
                reason = "engines failed: " + ", ".join(names)
            self.chat_area.add_message("system", f"Web search returned nothing - {reason}. Answering without web data")
            self.last_web_sources = []
            return ""
        
        self.last_web_sources = results

        context = "Internet search results:\n\n"
        for result in results:
            context += f"Title: {result['title']}\n"
            context += f"URL: {result['url']}\n"
            context += f"Snippet: {result['content']}\n\n"
        context += (
            "Base your answer on these results. If they do not cover the question, "
            "say that you could not find current information rather than stating "
            "that something does not exist. Distinguish professional critic reviews "
            "from player or user reviews, and say which ones the results cover.\n"
        )
        return context

    def send_message(self):
        self.last_web_sources = []
        prompt = self.input_bar.input_box.text()
        if not prompt and not self.attached_files:
            return

        attachments = self.attached_files
        self.attached_files = []
        self.update_attachment_label()

        text_files = [a for a in attachments if a["kind"] == "text"]
        image_files = [a for a in attachments if a["kind"] == "image"]

        stored_prompt = prompt
        if text_files:
            blocks = [
                f"--- Attached file: {a['name']} ---\n{a['text']}"
                for a in text_files
            ]
            stored_prompt = ("Attached files:\n\n" + "\n\n".join(blocks) + f"\n\n---\n\n{prompt}")

        if image_files:
            names = ", ".join(a["name"] for a in image_files)
            stored_prompt = f"[Attached images: {names}]\n\n{stored_prompt}"

        display = prompt or "(no message)"
        if attachments:
            display += "\n\n`attached: " + ", ".join(a["name"] for a in attachments) + "`"
        self.chat_area.add_message("user", display)

        append_message(self.project_id, "user", stored_prompt, self.host.token_count(stored_prompt))

        self.input_bar.input_box.clear()
        self.input_bar.send_button.setEnabled(False)
        self.input_bar.stop_button.setEnabled(True)
        self.vision_toggle.setEnabled(False)

        data = load_project(self.project_id) or {}

        project_context = self.build_project_context()
        ref_images = self.project_images()

        reserve = (len(image_files) + len(ref_images)) * IMAGE_TOKEN_COST
        if project_context:
            reserve += self.host.token_count(project_context)

        messages = self.host.message_budget(data.get("messages", []), reserve)

        all_images = ref_images + image_files
        if all_images and messages:
            content = [{"type": "text", "text": messages[-1]["content"]}]
            for a in all_images:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{a['media_type']};base64,{a['data']}"}
                })
            messages[-1] = {"role": "user", "content": content}

        if self.host.top_bar.web_toggle.isChecked():
            query = self.host.rewrite_search_query(data.get("messages", []), prompt)
            self.chat_area.add_message("system", f"Searching: {query}")
            web_context = self.build_web_context(query)
            if not web_context:
                web_context = (
                    "A web search was attempted for this message but returned nothing. "
                    "You have no current information. If the question is about recent "
                    "releases, events or products, say you could not verify it. Never claim "
                    "something does not exist just because you do not recognize it."
                )
            messages.insert(0, {"role": "system", "content": web_context})

        if project_context:
            messages.insert(0, {"role": "system", "content": project_context})

        self.inference_thread = self.host.new_inference_thread(messages, self.project_id)
        self.inference_thread.result_ready.connect(self.on_response)
        self.inference_thread.start()

    def stop_generation(self):
        if self.inference_thread is not None and self.inference_thread.isRunning():
            self.inference_thread.abort()
            self.input_bar.stop_button.setEnabled(False)

    def on_response(self, answer, _chat_id):
        stored_answer = answer
        if self.last_web_sources:
            source_lines = []
            for r in self.last_web_sources:
                source_lines.append(f"- {r['title']}")
            stored_answer = answer + "\n\n*Based on web sources:*\n" + "\n".join(source_lines)

        append_message(self.project_id, "assistant", stored_answer, self.host.token_count(stored_answer))
        self.chat_area.add_message("assistant", answer)

        if self.last_web_sources:
            lines = "\n".join(f"- [{r['title']}]({r['url']})" for r in self.last_web_sources)
            self.chat_area.add_message("system", "Sources:\n" + lines)

        self.input_bar.send_button.setEnabled(True)
        self.input_bar.stop_button.setEnabled(False)
        self.vision_toggle.setEnabled(self.host.mmproj_available)

    # Instructions injection
    def build_project_context(self):
        data = load_project(self.project_id) or {}
        notes = data.get("instructions", "").strip()
        if not notes:
            return ""
        name = data.get("name", "this project")
        return (
            f"Reference material for the project '{name}'. "
            f"Use it when relevant:\n\n{notes}"
        )

    def project_images(self):
        if not self.host.vision_active():
            return []
        out = []
        for path in image_paths(self.project_id):
            try:
                out.append(load_file(path))
            except Exception:
                continue
        return out

    def closeEvent(self, event):
            if self.inference_thread is not None and self.inference_thread.isRunning():
                self.inference_thread.abort()
                self.inference_thread.wait(3000)
    
            if self.host is not None:
                try:
                    self.host.top_bar.vision_button.toggled.disconnect(self.sync_from_host)
                    self.host.top_bar.web_toggle.toggled.disconnect(self.sync_from_host)
                except TypeError:
                    pass
    
            event.accept()





