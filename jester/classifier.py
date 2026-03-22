from csv import reader, writer
from glob import glob
from os import path
from os.path import basename, isfile
from shutil import move

from PyQt5.QtCore import Qt, QTimer, QObject, QEvent
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QLineEdit,
    QHBoxLayout, QVBoxLayout, QCheckBox, QSpinBox, QSizePolicy
)


class CandClassifier(QWidget):

    def __init__(self, directory, csv_path, extension, timescale):

        super().__init__()

        self._directory = directory
        self._csv_path = csv_path
        self._extension = extension
        self._timescale = timescale
        self._cand_plots = sorted(glob(path.join(directory, "*." + extension)))
        self._total_cands = len(self._cand_plots)
        self._current_cand = 0

        # Track classifications:
        #   { filename: { timescale: label, ... }, ... }
        self._classifications = {}
        # Track notes: { filename: note_text }
        self._notes = {}
        self._load_existing_csv()

        self._auto_enabled = False
        self._auto_speed_value = 2

        # Debounce resize events so image only rescales once window has settled
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._scale_image)

        main_box = QVBoxLayout()
        main_box.setContentsMargins(8, 4, 8, 6)
        main_box.setSpacing(3)

        # Image display
        self._plot_label = QLabel()
        self._plot_label.setAlignment(Qt.AlignCenter)
        self._plot_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._plot_label.setMaximumHeight(600)
        main_box.addWidget(self._plot_label)

        # Current candidate info
        current_box = QHBoxLayout()
        self._current_cand_select = QLineEdit()
        self._current_cand_select.setFixedSize(60, 24)
        self._current_cand_select.setText("1")
        self._current_cand_select.setStyleSheet("font-size: 13px;")
        self._current_cand_select.returnPressed.connect(self._set_cand)
        self._current_cand_select.installEventFilter(self)
        current_box.addWidget(self._current_cand_select)
        self._cand_label = QLabel()
        self._cand_label.setStyleSheet("font-size: 13px;")
        self._cand_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        current_box.addWidget(self._cand_label)
        current_box.addStretch()

        # Timescale indicator
        timescale_label = QLabel(f"Timescale: {self._timescale}")
        timescale_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #2980b9;")
        current_box.addWidget(timescale_label)

        main_box.addLayout(current_box)

        # --- Classification buttons ---
        classify_box = QHBoxLayout()
        classify_box.setContentsMargins(20, 2, 0, 2)
        classify_box.setSpacing(10)

        self._real_button = self._make_button("Real", "#2ecc71", lambda: self._classify("real"))
        self._not_variable_button = self._make_button("Not variable", "#f39c12", lambda: self._classify("not variable"))
        self._artefact_button = self._make_button("Artefact", "#e74c3c", lambda: self._classify("artefact"))

        classify_box.addWidget(self._real_button)
        classify_box.addWidget(self._not_variable_button)
        classify_box.addWidget(self._artefact_button)
        classify_box.addStretch()
        main_box.addLayout(classify_box)

        # --- Status label showing current classification ---
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("font-size: 12px; color: #555;")
        self._status_label.setContentsMargins(20, 0, 0, 0)
        main_box.addWidget(self._status_label)

        # --- Notes box ---
        notes_box = QHBoxLayout()
        notes_box.setContentsMargins(20, 0, 0, 0)
        notes_label = QLabel("Notes:")
        notes_label.setStyleSheet("font-size: 12px;")
        notes_label.setFixedWidth(45)
        notes_box.addWidget(notes_label)
        self._notes_edit = QLineEdit()
        self._notes_edit.setStyleSheet("font-size: 12px;")
        self._notes_edit.setFixedHeight(24)
        self._notes_edit.setPlaceholderText("Optional note for this source...")
        self._notes_edit.textChanged.connect(self._save_note)
        self._notes_edit.installEventFilter(self)
        notes_box.addWidget(self._notes_edit)
        main_box.addLayout(notes_box)

        # --- Navigation ---
        nav_box = QHBoxLayout()
        self._skip_start_button = self._make_nav_button("|<", self._skip_start_press, 28)
        self._prev_skip_button = self._make_nav_button("<<", self._previous_skip_press, 36)
        self._prev_button = self._make_nav_button("<", self._previous_press)
        self._next_button = self._make_nav_button(">", self._next_press)
        self._next_skip_button = self._make_nav_button(">>", self._next_skip_press, 36)
        self._skip_end_button = self._make_nav_button(">|", self._skip_end_press, 28)

        for btn in [self._skip_start_button, self._prev_skip_button,
                    self._prev_button, self._next_button,
                    self._next_skip_button, self._skip_end_button]:
            nav_box.addWidget(btn)
        nav_box.addStretch()

        # Auto-advance
        self._auto_timer = QTimer()
        self._auto_timer.timeout.connect(self._next_press)
        auto_label = QLabel("Auto:")
        auto_label.setStyleSheet("font-size: 12px;")
        nav_box.addWidget(auto_label)
        self._auto_enable = QCheckBox()
        self._auto_enable.stateChanged.connect(self._enable_auto)
        nav_box.addWidget(self._auto_enable)
        self._auto_speed = QSpinBox()
        self._auto_speed.setMinimum(1)
        self._auto_speed.setMaximum(10)
        self._auto_speed.setValue(self._auto_speed_value)
        self._auto_speed.setFixedHeight(24)
        self._auto_speed.valueChanged.connect(self._change_auto_speed)
        nav_box.addWidget(self._auto_speed)
        speed_label = QLabel("img/s")
        speed_label.setStyleSheet("font-size: 12px;")
        nav_box.addWidget(speed_label)

        main_box.addLayout(nav_box)

        # Summary counts
        summary_box = QHBoxLayout()
        self._summary_label = QLabel("Classified: 0")
        self._summary_label.setStyleSheet("font-size: 12px; color: #333;")
        summary_box.addWidget(self._summary_label)
        summary_box.addStretch()
        main_box.addLayout(summary_box)

        # Help text
        help_label = QLabel("Keys: Z=prev  X=next  1=Real  2=Not variable  3=Artefact  V=auto  |  Press Esc to exit Notes field")
        help_label.setStyleSheet("font-size: 11px; color: #888;")
        main_box.addWidget(help_label)

        self.setLayout(main_box)
        self.setWindowTitle(f"Image Classifier  —  Timescale: {self._timescale}")
        self.resize(1000, 750)
        self.show()
        self.setFocus()  # ensure shortcuts work immediately, not the candidate field

        if self._total_cands > 0:
            self._show_cand(0)
        else:
            self._cand_label.setText("No images found in directory")

    # --- Helpers ---

    def _make_button(self, text, color, callback):
        btn = QPushButton(text)
        btn.setFixedSize(100, 32)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                font-weight: bold;
                font-size: 13px;
                border-radius: 4px;
            }}
            QPushButton[selected="true"] {{
                border: 3px solid black;
            }}
        """)
        btn.clicked.connect(callback)
        return btn

    def _make_nav_button(self, text, callback, width=None):
        btn = QPushButton(text)
        if width:
            btn.setFixedWidth(width)
        btn.clicked.connect(callback)
        return btn

    # --- CSV persistence ---
    #
    # CSV format:
    #   filename,    1s,       10s,      30s,      notes
    #   source_A,    real,     artefact, real,     interesting shape
    #   source_B,    artefact, ,         real,
    #
    # The header row lists all timescales as columns, with notes last.
    # Each new timescale run adds a new column before notes.

    def _load_existing_csv(self):
        csv_path = self._csv_path
        if not isfile(csv_path):
            return

        with open(csv_path, "r") as f:
            r = reader(f, delimiter=",")
            rows = list(r)

        if not rows:
            return

        header = rows[0]
        if len(header) < 2:
            return

        # Strip "notes" from the end of the header if present
        has_notes = header[-1].strip().lower() == "notes"
        timescales = header[1:-1] if has_notes else header[1:]

        for row in rows[1:]:
            if not row:
                continue
            filename = row[0]
            ts_dict = {}
            for i, ts in enumerate(timescales):
                col = i + 1
                label = row[col] if col < len(row) else ""
                if ts:
                    ts_dict[ts] = label
            self._classifications[filename] = ts_dict
            if has_notes:
                notes_col = len(timescales) + 1
                self._notes[filename] = row[notes_col] if notes_col < len(row) else ""

    def _save_classification(self, cand_name):
        csv_path = self._csv_path
        tmp_path = csv_path + ".tmp"

        # Collect all timescales seen, preserving order of first appearance
        all_timescales = []
        for ts_dict in self._classifications.values():
            for ts in ts_dict:
                if ts not in all_timescales:
                    all_timescales.append(ts)
        if self._timescale not in all_timescales:
            all_timescales.append(self._timescale)

        # Header row — notes always last
        header = ["filename"] + all_timescales + ["notes"]

        # Data rows, sorted by filename
        data_rows = []
        for filename, ts_dict in sorted(self._classifications.items()):
            note = self._notes.get(filename, "")
            row = [filename] + [ts_dict.get(ts, "") for ts in all_timescales] + [note]
            data_rows.append(row)

        with open(tmp_path, "w", newline="") as f:
            w = writer(f, delimiter=",")
            w.writerow(header)
            w.writerows(data_rows)

        move(tmp_path, csv_path)

    # --- Classification logic ---

    def _save_note(self):
        if self._total_cands == 0:
            return
        cand_name = basename(self._cand_plots[self._current_cand])
        self._notes[cand_name] = self._notes_edit.text()
        if cand_name not in self._classifications:
            self._classifications[cand_name] = {}
        self._save_classification(cand_name)

    def _classify(self, label):
        if self._total_cands == 0:
            return

        cand_name = basename(self._cand_plots[self._current_cand])
        if cand_name not in self._classifications:
            self._classifications[cand_name] = {}
        self._classifications[cand_name][self._timescale] = label
        self._save_classification(cand_name)
        self._update_status()
        self._update_button_highlight()
        self._update_summary()

    def _update_status(self):
        if self._total_cands == 0:
            return
        cand_name = basename(self._cand_plots[self._current_cand])
        ts_dict = self._classifications.get(cand_name, {})

        # Show label for current timescale prominently, others as context
        current_label = ts_dict.get(self._timescale, "—")
        other_parts = [f"{ts}: {lbl}" for ts, lbl in ts_dict.items() if ts != self._timescale and lbl]
        status = f"[{self._timescale}] {current_label}"
        if other_parts:
            status += "   |   Other timescales: " + "  ".join(other_parts)
        self._status_label.setText(status)

    def _update_button_highlight(self):
        if self._total_cands == 0:
            return
        cand_name = basename(self._cand_plots[self._current_cand])
        label = self._classifications.get(cand_name, {}).get(self._timescale, "")

        self._real_button.setProperty("selected", label == "real")
        self._not_variable_button.setProperty("selected", label == "not variable")
        self._artefact_button.setProperty("selected", label == "artefact")

        for btn in [self._real_button, self._not_variable_button, self._artefact_button]:
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _update_summary(self):
        # Count only classifications for the current timescale
        labels = [
            ts_dict.get(self._timescale, "")
            for ts_dict in self._classifications.values()
        ]
        total_classified = sum(1 for l in labels if l)
        real_count = sum(1 for l in labels if l == "real")
        not_variable_count = sum(1 for l in labels if l == "not variable")
        artefact_count = sum(1 for l in labels if l == "artefact")
        self._summary_label.setText(
            f"[{self._timescale}]  Classified: {total_classified} / {self._total_cands}   "
            f"(Real: {real_count}  |  Not variable: {not_variable_count}  |  Artefact: {artefact_count})"
        )

    # --- Navigation ---

    def _show_cand(self, idx=0):
        if not (0 <= idx < self._total_cands):
            return

        self._current_cand = idx
        self._current_pixmap = QPixmap(self._cand_plots[idx])
        self._scale_image()

        self._current_cand_select.setText(str(idx + 1))
        self._cand_label.setText(f"of {self._total_cands}: {basename(self._cand_plots[idx])}")
        self._update_status()
        self._update_button_highlight()
        # Load existing note for this candidate
        cand_name = basename(self._cand_plots[idx])
        self._notes_edit.setText(self._notes.get(cand_name, ""))

    def _scale_image(self):
        if not hasattr(self, "_current_pixmap") or self._current_pixmap is None:
            return
        # Use the label's actual allocated size, capped to avoid over-expansion
        w = self._plot_label.width()
        h = self._plot_label.height()
        if w < 10 or h < 10:
            return
        scaled = self._current_pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._plot_label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._total_cands > 0:
            self._resize_timer.start(100)  # wait 100ms after last resize before rescaling

    def _set_cand(self):
        self._plot_label.setFocus()
        text = self._current_cand_select.text()
        try:
            self._show_cand(int(text) - 1)
        except ValueError:
            self._show_cand(0)

    def _next_press(self, event=None):
        self._show_cand(self._current_cand + 1)

    def _previous_press(self, event=None):
        self._show_cand(self._current_cand - 1)

    def _previous_skip_press(self, event=None):
        self._show_cand(max(self._current_cand - 5, 0))

    def _next_skip_press(self, event=None):
        self._show_cand(min(self._current_cand + 5, self._total_cands - 1))

    def _skip_start_press(self, event=None):
        self._show_cand(0)

    def _skip_end_press(self, event=None):
        self._show_cand(self._total_cands - 1)

    # --- Auto-advance ---

    def _enable_auto(self, state=None):
        self._auto_enabled = not self._auto_enabled
        if self._auto_enabled:
            self._auto_timer.start(int(1000 / self._auto_speed.value()))
        else:
            self._auto_timer.stop()

    def _change_auto_speed(self, value):
        self._auto_speed_value = value
        if self._auto_enabled:
            self._auto_timer.start(int(1000 / value))

    # --- Event filter (notes field keyboard handling) ---

    def eventFilter(self, obj, event):
        """Intercept key presses in text fields.

        Escape releases focus back to the main widget so all shortcuts work
        again. Every other key is handled normally by the line edit.
        """
        if obj in (self._notes_edit, self._current_cand_select) and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.setFocus()
                return True  # consume the event
        return super().eventFilter(obj, event)

    # --- Keyboard shortcuts ---

    def keyPressEvent(self, event):
        # Don't steal keypresses while the user is typing in a text field
        if self._notes_edit.hasFocus() or self._current_cand_select.hasFocus():
            super().keyPressEvent(event)
            return

        key = event.key()

        if self._auto_enabled and key not in (Qt.Key_V,):
            self._auto_enable.nextCheckState()

        route = {
            Qt.Key_Z: self._previous_press,
            Qt.Key_X: self._next_press,
            Qt.Key_PageDown: self._previous_skip_press,
            Qt.Key_PageUp: self._next_skip_press,
            Qt.Key_Home: self._skip_start_press,
            Qt.Key_End: self._skip_end_press,
            Qt.Key_1: lambda: self._classify("real"),
            Qt.Key_2: lambda: self._classify("not variable"),
            Qt.Key_3: lambda: self._classify("artefact"),
            Qt.Key_V: self._auto_enable.nextCheckState,
        }

        fn = route.get(key)
        if fn:
            fn()