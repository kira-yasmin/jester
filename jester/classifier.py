from csv import reader, writer
from glob import glob
from os import path
from os.path import basename, isfile
from shutil import move

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QLineEdit,
    QHBoxLayout, QVBoxLayout, QCheckBox, QSpinBox
)


class CandClassifier(QWidget):

    def __init__(self, directory, output, extension):

        super().__init__()

        self._directory = directory
        self._output_file_name = output
        self._extension = extension
        self._cand_plots = sorted(glob(path.join(directory, "*." + extension)))
        self._total_cands = len(self._cand_plots)
        self._current_cand = 0

        # Track classifications: dict mapping filename -> (looks_real, worth_investigating)
        self._classifications = {}
        self._load_existing_csv()

        self._auto_enabled = False
        self._auto_speed_value = 2

        main_box = QVBoxLayout()
        main_box.setContentsMargins(10, 5, 10, 10)
        main_box.setSpacing(5)

        # Image display
        self._plot_label = QLabel()
        self._plot_label.setAlignment(Qt.AlignCenter)
        main_box.addWidget(self._plot_label)

        # Current candidate info
        current_box = QHBoxLayout()
        self._current_cand_select = QLineEdit()
        self._current_cand_select.setFixedSize(80, 28)
        self._current_cand_select.setText("1")
        self._current_cand_select.setStyleSheet("font-size: 16px;")
        self._current_cand_select.returnPressed.connect(self._set_cand)
        current_box.addWidget(self._current_cand_select)
        self._cand_label = QLabel()
        self._cand_label.setStyleSheet("font-size: 16px;")
        self._cand_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        current_box.addWidget(self._cand_label)
        current_box.addStretch()
        main_box.addLayout(current_box)

        # --- Classification buttons ---
        classify_box = QVBoxLayout()
        classify_box.setSpacing(8)

        # Row 1: Looks real?
        real_row = QHBoxLayout()
        real_label = QLabel("Looks real?")
        real_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        real_label.setFixedWidth(160)
        real_row.addWidget(real_label)

        self._real_yes = self._make_button("Yes", "#2ecc71", lambda: self._classify("real", "yes"))
        self._real_maybe = self._make_button("Maybe", "#f39c12", lambda: self._classify("real", "maybe"))
        self._real_no = self._make_button("No", "#e74c3c", lambda: self._classify("real", "no"))

        for btn in [self._real_yes, self._real_maybe, self._real_no]:
            real_row.addWidget(btn)
        real_row.addStretch()
        classify_box.addLayout(real_row)

        # Row 2: Worth investigating?
        invest_row = QHBoxLayout()
        invest_label = QLabel("Worth investigating?")
        invest_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        invest_label.setFixedWidth(160)
        invest_row.addWidget(invest_label)

        self._invest_yes = self._make_button("Yes", "#2ecc71", lambda: self._classify("investigate", "yes"))
        self._invest_maybe = self._make_button("Maybe", "#f39c12", lambda: self._classify("investigate", "maybe"))
        self._invest_no = self._make_button("No", "#e74c3c", lambda: self._classify("investigate", "no"))

        for btn in [self._invest_yes, self._invest_maybe, self._invest_no]:
            invest_row.addWidget(btn)
        invest_row.addStretch()
        classify_box.addLayout(invest_row)

        main_box.addLayout(classify_box)

        # --- Status label showing current classification ---
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("font-size: 14px; color: #555;")
        main_box.addWidget(self._status_label)

        # --- Navigation ---
        nav_box = QHBoxLayout()
        self._skip_start_button = self._make_nav_button("|<", self._skip_start_press, 30)
        self._prev_skip_button = self._make_nav_button("<<", self._previous_skip_press, 45)
        self._prev_button = self._make_nav_button("<", self._previous_press)
        self._next_button = self._make_nav_button(">", self._next_press)
        self._next_skip_button = self._make_nav_button(">>", self._next_skip_press, 45)
        self._skip_end_button = self._make_nav_button(">|", self._skip_end_press, 30)

        for btn in [self._skip_start_button, self._prev_skip_button,
                    self._prev_button, self._next_button,
                    self._next_skip_button, self._skip_end_button]:
            nav_box.addWidget(btn)
        nav_box.addStretch()

        # Auto-advance
        self._auto_timer = QTimer()
        self._auto_timer.timeout.connect(self._next_press)
        auto_label = QLabel("Auto:")
        auto_label.setStyleSheet("font-size: 14px;")
        nav_box.addWidget(auto_label)
        self._auto_enable = QCheckBox()
        self._auto_enable.stateChanged.connect(self._enable_auto)
        nav_box.addWidget(self._auto_enable)
        self._auto_speed = QSpinBox()
        self._auto_speed.setMinimum(1)
        self._auto_speed.setMaximum(10)
        self._auto_speed.setValue(self._auto_speed_value)
        self._auto_speed.valueChanged.connect(self._change_auto_speed)
        nav_box.addWidget(self._auto_speed)
        speed_label = QLabel("img/s")
        speed_label.setStyleSheet("font-size: 14px;")
        nav_box.addWidget(speed_label)

        main_box.addLayout(nav_box)

        # Summary counts
        summary_box = QHBoxLayout()
        self._summary_label = QLabel("Classified: 0")
        self._summary_label.setStyleSheet("font-size: 14px; color: #333;")
        summary_box.addWidget(self._summary_label)
        summary_box.addStretch()
        main_box.addLayout(summary_box)

        # Help text
        help_label = QLabel("Keys: Z=prev  X=next  1=Real:Yes  2=Real:Maybe  3=Real:No  4=Invest:Yes  5=Invest:Maybe  6=Invest:No  V=auto")
        help_label.setStyleSheet("font-size: 12px; color: #888;")
        main_box.addWidget(help_label)

        self.setLayout(main_box)
        self.setWindowTitle("Image Classifier")
        self.setGeometry(150, 150, 960, 780)
        self.show()

        if self._total_cands > 0:
            self._show_cand(0)
        else:
            self._cand_label.setText("No images found in directory")

    # --- Helpers ---

    def _make_button(self, text, color, callback):
        btn = QPushButton(text)
        btn.setFixedSize(120, 40)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                font-weight: bold;
                font-size: 16px;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                opacity: 0.85;
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

    def _load_existing_csv(self):
        csv_path = path.join(self._directory, self._output_file_name)
        if isfile(csv_path):
            with open(csv_path, "r") as f:
                r = reader(f, delimiter=",")
                for row in r:
                    if len(row) >= 3:
                        self._classifications[row[0]] = {"real": row[1], "investigate": row[2]}

    def _save_classification(self, cand_name):
        csv_path = path.join(self._directory, self._output_file_name)
        tmp_path = csv_path + ".tmp"
        classification = self._classifications.get(cand_name, {})

        # Rewrite entire CSV (keeps it clean and consistent)
        rows = []
        written = False
        if isfile(csv_path):
            with open(csv_path, "r") as f:
                r = reader(f, delimiter=",")
                for row in r:
                    if len(row) >= 1 and row[0] == cand_name:
                        rows.append([cand_name,
                                     classification.get("real", ""),
                                     classification.get("investigate", "")])
                        written = True
                    else:
                        rows.append(row)

        if not written:
            rows.append([cand_name,
                         classification.get("real", ""),
                         classification.get("investigate", "")])

        with open(tmp_path, "w", newline="") as f:
            w = writer(f, delimiter=",")
            w.writerows(rows)

        move(tmp_path, csv_path)

    # --- Classification logic ---

    def _classify(self, question, answer):
        if self._total_cands == 0:
            return

        cand_name = basename(self._cand_plots[self._current_cand])
        if cand_name not in self._classifications:
            self._classifications[cand_name] = {}
        self._classifications[cand_name][question] = answer
        self._save_classification(cand_name)
        self._update_status()
        self._update_summary()

    def _update_status(self):
        if self._total_cands == 0:
            return
        cand_name = basename(self._cand_plots[self._current_cand])
        c = self._classifications.get(cand_name, {})
        real = c.get("real", "—")
        invest = c.get("investigate", "—")
        self._status_label.setText(f"Current: Looks real = {real}   |   Worth investigating = {invest}")

    def _update_summary(self):
        total_classified = sum(
            1 for c in self._classifications.values()
            if c.get("real") or c.get("investigate")
        )
        self._summary_label.setText(f"Classified: {total_classified} / {self._total_cands}")

    # --- Navigation ---

    def _show_cand(self, idx=0):
        if not (0 <= idx < self._total_cands):
            return

        self._current_cand = idx
        cand_map = QPixmap(self._cand_plots[idx])

        # Scale image to fit a fixed display area, preserving aspect ratio
        scaled = cand_map.scaled(900, 550, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._plot_label.setPixmap(scaled)

        self._current_cand_select.setText(str(idx + 1))
        self._cand_label.setText(f"of {self._total_cands}: {basename(self._cand_plots[idx])}")
        self._update_status()

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

    # --- Keyboard shortcuts ---

    def keyPressEvent(self, event):
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
            # Looks real
            Qt.Key_1: lambda: self._classify("real", "yes"),
            Qt.Key_2: lambda: self._classify("real", "maybe"),
            Qt.Key_3: lambda: self._classify("real", "no"),
            # Worth investigating
            Qt.Key_4: lambda: self._classify("investigate", "yes"),
            Qt.Key_5: lambda: self._classify("investigate", "maybe"),
            Qt.Key_6: lambda: self._classify("investigate", "no"),
            # Auto toggle
            Qt.Key_V: self._auto_enable.nextCheckState,
        }

        fn = route.get(key)
        if fn:
            fn()
