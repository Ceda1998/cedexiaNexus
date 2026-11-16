"""Edit one library model's settings without switching the chat model."""
from pathlib import Path

from .i18n import t

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)


class ModelSettings(QWidget):
    def __init__(self, runner):
        super().__init__()
        self.runner = runner
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.library = QListWidget()
        self.library.setAccessibleName(t("Modellbibliothek"))
        layout.addWidget(self.library, 1)

        actions = QHBoxLayout()
        self.add = QPushButton(t("GGUF hinzufügen …"))
        self.add.setProperty("primary", True)
        self.add.clicked.connect(self.import_models)
        self.remove = QPushButton(t("Auswahl entfernen"))
        self.remove.clicked.connect(lambda: self.runner.remove_model(self.selected_path()))
        self.use = QPushButton(t("Für Chat und Geräteabgleich verwenden"))
        self.use.clicked.connect(lambda: self.runner.select_model(self.selected_path()))
        actions.addWidget(self.add)
        actions.addWidget(self.remove)
        actions.addWidget(self.use)
        actions.addStretch()
        layout.addLayout(actions)
        self.default = QPushButton(t('Als Standardmodell verwenden'))
        self.default.clicked.connect(lambda: self.runner.set_default_model(self.selected_path()))
        layout.addWidget(self.default, alignment=Qt.AlignmentFlag.AlignLeft)

        self.path = QLabel()
        self.path.setTextFormat(Qt.TextFormat.PlainText)
        self.path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path.setWordWrap(True)
        layout.addWidget(self.path)
        form = QFormLayout()
        form.setSpacing(12)
        self.fields = {}
        for key, title, minimum, maximum in (
            ("context", t("Kontexttokens"), 512, 131072),
            ("predict", t("Ausgabetokens"), 0, 8192),
        ):
            field = QSpinBox()
            field.setRange(minimum, maximum)
            if key == "predict":
                field.setSpecialValueText(t("Bis Kontextgrenze"))
            field.valueChanged.connect(lambda value, name=key: self.save(name, -2 if value == 0 else value))
            form.addRow(title, field)
            self.fields[key] = field
        options = {"reasoning": t("Reasoning anfordern (modellabhängig)")}
        if runner.windows:
            options["windows_cpu"] = t("CPU statt NVIDIA-GPU verwenden")
        for key, title in options.items():
            field = QCheckBox(title)
            field.toggled.connect(lambda value, name=key: self.save(name, value))
            form.addRow(field)
            self.fields[key] = field
        layout.addLayout(form)
        notes = QLabel(t("Änderungen gelten ab dem nächsten Modellstart."))
        notes.setObjectName("libraryStatus")
        layout.addWidget(notes)

        self.library.currentItemChanged.connect(self.show_settings)
        runner.library_changed.connect(self.refresh_library)
        runner.model_changed.connect(self.show_settings)
        runner.busy_changed.connect(self.show_settings)
        self.refresh_library()

    def selected_path(self):
        item = self.library.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def select_path(self, path):
        for index in range(self.library.count()):
            if self.library.item(index).data(Qt.ItemDataRole.UserRole) == str(path):
                self.library.setCurrentRow(index)
                break

    def refresh_library(self):
        previous = self.selected_path() or self.runner.model
        with QSignalBlocker(self.library):
            self.library.clear()
            for path in self.runner.models:
                model = Path(path)
                suffix = t(' · Standard') if path == self.runner.settings.value('default_model_path', '') else ''
                item = QListWidgetItem(model.name + suffix)
                item.setData(Qt.ItemDataRole.UserRole, path)
                item.setToolTip(path)
                item.setStatusTip(path)
                self.library.addItem(item)
            if self.library.count():
                self.library.setCurrentRow(0)
                self.select_path(previous)
        self.show_settings()

    def import_models(self):
        paths, _ = QFileDialog.getOpenFileNames(self, t("Lokale Modelle"), "", "GGUF (*.gguf)")
        if paths:
            self.runner.add_models(paths)
            self.select_path(Path(paths[0]).absolute())
            if self.runner.model is None:
                self.runner.select_model(paths[0])

    def show_settings(self, *_):
        path = self.selected_path()
        editable = bool(path) and not (self.runner.busy or self.runner.external_busy)
        self.add.setEnabled(not (self.runner.busy or self.runner.external_busy))
        self.remove.setEnabled(editable)
        self.use.setEnabled(editable and path != str(self.runner.model))
        self.default.setEnabled(editable and path != self.runner.settings.value('default_model_path', ''))
        self.path.setText(path or t("Füge eine lokale GGUF-Datei hinzu."))
        for key, field in self.fields.items():
            value = self.runner.model_setting(path, key)
            with QSignalBlocker(field):
                if isinstance(field, QCheckBox):
                    field.setChecked(value)
                else:
                    field.setValue(max(0, value) if key == "predict" else value)
            field.setEnabled(editable)

    def save(self, key, value):
        if (path := self.selected_path()) and not (self.runner.busy or self.runner.external_busy):
            self.runner.set_model_setting(path, key, value)
