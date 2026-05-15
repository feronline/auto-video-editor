"""PyQt6 arayüz — sürükle-bırak, ayarlar, küfür listesi, ilerleme."""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QSpinBox, QTextEdit,
    QVBoxLayout, QWidget,
)

from .config import EditConfig, OUTPUT_DIR
from .pipeline import run_pipeline


class DropArea(QLabel):
    fileDropped = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__("Videoyu buraya sürükle-bırak\nveya tıklayıp seç")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setStyleSheet("""
            QLabel {
                border: 2px dashed #888;
                border-radius: 10px;
                padding: 40px;
                font-size: 16px;
                color: #444;
                background: #fafafa;
            }
            QLabel:hover { background: #f0f0f0; }
        """)
        self.setMinimumHeight(140)

    def mousePressEvent(self, ev) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Video seç", "", "Video (*.mkv *.mp4 *.mov *.avi)"
        )
        if path:
            self.fileDropped.emit(path)

    def dragEnterEvent(self, ev: QDragEnterEvent) -> None:
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev: QDropEvent) -> None:
        urls = ev.mimeData().urls()
        if urls:
            self.fileDropped.emit(urls[0].toLocalFile())


class Worker(QThread):
    log = pyqtSignal(str)
    progress = pyqtSignal(float, str)
    done = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, video: Path, cfg: EditConfig) -> None:
        super().__init__()
        self.video = video
        self.cfg = cfg

    def run(self) -> None:
        try:
            parts = run_pipeline(
                self.video, self.cfg,
                log=lambda s: self.log.emit(s),
                progress=lambda p, s: self.progress.emit(p, s),
            )
            self.done.emit([str(p) for p in parts])
        except Exception as e:
            self.error.emit(f"{e}\n\n{traceback.format_exc()}")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AutoEditor — Oyun videosu otomatik editör")
        self.resize(900, 760)

        self.video_path: Path | None = None
        self.worker: Worker | None = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # Sürükle-bırak
        self.drop = DropArea()
        self.drop.fileDropped.connect(self.set_video)
        root.addWidget(self.drop)

        self.video_label = QLabel("Henüz video seçilmedi.")
        root.addWidget(self.video_label)

        # Ayarlar grubu
        settings_grp = QGroupBox("Ayarlar")
        form = QFormLayout(settings_grp)

        self.mic_track = QSpinBox()
        self.mic_track.setRange(0, 7)
        self.mic_track.setValue(1)
        form.addRow("Mikrofon track indeksi (0-bazlı)", self.mic_track)

        self.game_track = QSpinBox()
        self.game_track.setRange(0, 7)
        self.game_track.setValue(0)
        form.addRow("Oyun sesi track indeksi", self.game_track)

        self.include_game = QCheckBox("Oyun sesini çıktıda tut (mic ile mix)")
        self.include_game.setChecked(True)
        form.addRow(self.include_game)

        self.game_gain = QDoubleSpinBox()
        self.game_gain.setRange(0.0, 2.0)
        self.game_gain.setSingleStep(0.05)
        self.game_gain.setValue(1.0)
        form.addRow("Oyun sesi seviyesi (1.0 = orijinal)", self.game_gain)

        self.silence_db = QDoubleSpinBox()
        self.silence_db.setRange(-80.0, 0.0)
        self.silence_db.setValue(-52.0)
        self.silence_db.setSuffix(" dB")
        form.addRow("Sessizlik eşiği", self.silence_db)

        self.min_silence = QDoubleSpinBox()
        self.min_silence.setRange(0.1, 5.0)
        self.min_silence.setSingleStep(0.1)
        self.min_silence.setValue(0.9)
        self.min_silence.setSuffix(" s")
        form.addRow("Min. sessizlik süresi", self.min_silence)

        self.pad_before = QDoubleSpinBox()
        self.pad_before.setRange(0.0, 1.0)
        self.pad_before.setSingleStep(0.05)
        self.pad_before.setValue(0.25)
        self.pad_before.setSuffix(" s")
        form.addRow("Konuşma öncesi padding", self.pad_before)

        self.pad_after = QDoubleSpinBox()
        self.pad_after.setRange(0.0, 1.0)
        self.pad_after.setSingleStep(0.05)
        self.pad_after.setValue(0.40)
        self.pad_after.setSuffix(" s")
        form.addRow("Konuşma sonrası padding", self.pad_after)

        self.split_enabled = QCheckBox("Uzun videoyu parçalara böl")
        self.split_enabled.setChecked(True)
        self.split_enabled.toggled.connect(self._toggle_split)
        form.addRow(self.split_enabled)

        self.target_min = QDoubleSpinBox()
        self.target_min.setRange(1.0, 60.0)
        self.target_min.setValue(15.0)
        self.target_min.setSuffix(" dk")
        form.addRow("Hedef parça uzunluğu", self.target_min)

        root.addWidget(settings_grp)

        # Sansür
        censor_grp = QGroupBox("Küfür sansürü")
        censor_lay = QVBoxLayout(censor_grp)
        self.enable_censor = QCheckBox("Etkin (yavaşlatır: transkripsiyon yapar)")
        self.enable_censor.setChecked(False)
        censor_lay.addWidget(self.enable_censor)
        censor_lay.addWidget(QLabel("Sansürlenecek kelimeler (her satıra bir tane, kısmi eşleşme):"))
        self.censor_words = QPlainTextEdit()
        self.censor_words.setMaximumHeight(110)
        self.censor_words.setPlaceholderText("amk\nsiktir\n...")
        censor_lay.addWidget(self.censor_words)
        root.addWidget(censor_grp)

        # Intro/outro
        io_grp = QGroupBox("Intro / Outro (opsiyonel)")
        io_lay = QFormLayout(io_grp)
        self.intro_path = QLineEdit()
        btn_intro = QPushButton("Seç...")
        btn_intro.clicked.connect(lambda: self._pick(self.intro_path))
        row1 = QHBoxLayout(); row1.addWidget(self.intro_path); row1.addWidget(btn_intro)
        w1 = QWidget(); w1.setLayout(row1)
        io_lay.addRow("Intro:", w1)

        self.outro_path = QLineEdit()
        btn_outro = QPushButton("Seç...")
        btn_outro.clicked.connect(lambda: self._pick(self.outro_path))
        row2 = QHBoxLayout(); row2.addWidget(self.outro_path); row2.addWidget(btn_outro)
        w2 = QWidget(); w2.setLayout(row2)
        io_lay.addRow("Outro:", w2)
        root.addWidget(io_grp)

        # Çalıştır + progress + log
        self.btn_run = QPushButton("İŞLE")
        self.btn_run.setStyleSheet("font-size: 16px; padding: 10px; font-weight: bold;")
        self.btn_run.clicked.connect(self.start)
        root.addWidget(self.btn_run)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        root.addWidget(self.progress)
        self.stage_label = QLabel("")
        root.addWidget(self.stage_label)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(200)
        root.addWidget(self.log_view)

    def _toggle_split(self, on: bool) -> None:
        self.target_min.setEnabled(on)

    def _pick(self, line: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Video seç", "", "Video (*.mkv *.mp4 *.mov *.avi)"
        )
        if path:
            line.setText(path)

    def set_video(self, path: str) -> None:
        self.video_path = Path(path)
        self.video_label.setText(f"Seçili: {self.video_path.name}")

    def build_cfg(self) -> EditConfig:
        words = [
            w.strip() for w in self.censor_words.toPlainText().splitlines()
            if w.strip()
        ]
        return EditConfig(
            mic_track_index=self.mic_track.value(),
            game_track_index=self.game_track.value(),
            include_game_audio=self.include_game.isChecked(),
            game_audio_gain=self.game_gain.value(),
            silence_threshold_db=self.silence_db.value(),
            min_silence_duration=self.min_silence.value(),
            padding_before=self.pad_before.value(),
            padding_after=self.pad_after.value(),
            split_enabled=self.split_enabled.isChecked(),
            target_clip_minutes=self.target_min.value(),
            enable_censor=self.enable_censor.isChecked(),
            censor_words=words,
            intro_path=self.intro_path.text().strip() or None,
            outro_path=self.outro_path.text().strip() or None,
        )

    def start(self) -> None:
        if not self.video_path or not self.video_path.exists():
            QMessageBox.warning(self, "Eksik", "Önce bir video seç.")
            return
        if self.worker and self.worker.isRunning():
            return
        self.log_view.clear()
        self.progress.setValue(0)
        self.btn_run.setEnabled(False)
        cfg = self.build_cfg()
        self.worker = Worker(self.video_path, cfg)
        self.worker.log.connect(self.on_log)
        self.worker.progress.connect(self.on_progress)
        self.worker.done.connect(self.on_done)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def on_log(self, msg: str) -> None:
        self.log_view.append(msg)

    def on_progress(self, p: float, stage: str) -> None:
        self.progress.setValue(int(p * 100))
        self.stage_label.setText(stage)

    def on_done(self, parts: list) -> None:
        self.btn_run.setEnabled(True)
        self.progress.setValue(100)
        QMessageBox.information(
            self, "Bitti",
            f"{len(parts)} parça üretildi.\n\nKonum: {OUTPUT_DIR}"
        )

    def on_error(self, msg: str) -> None:
        self.btn_run.setEnabled(True)
        self.log_view.append(f"\n[HATA]\n{msg}")
        QMessageBox.critical(self, "Hata", msg.split("\n\n")[0])


def main() -> None:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
