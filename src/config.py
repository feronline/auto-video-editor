"""Varsayılan ayarlar ve sabitler."""
import sys
from dataclasses import dataclass, field
from pathlib import Path


def _root() -> Path:
    """PyInstaller bundle'da .exe'nin yanını, kaynak çalıştırmada proje kökünü döndür."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


ROOT = _root()
TEMP_DIR = ROOT / "temp"
OUTPUT_DIR = ROOT / "output"
TEMPLATES_DIR = ROOT / "templates"
MODELS_DIR = ROOT / "models"

for d in (TEMP_DIR, OUTPUT_DIR, TEMPLATES_DIR, MODELS_DIR):
    d.mkdir(exist_ok=True)


@dataclass
class EditConfig:
    mic_track_index: int = 1
    game_track_index: int = 0
    include_game_audio: bool = True
    game_audio_gain: float = 1.0
    silence_threshold_db: float = -52.0
    min_silence_duration: float = 0.9
    padding_before: float = 0.25
    padding_after: float = 0.40
    split_enabled: bool = True
    target_clip_minutes: float = 15.0
    split_min_minutes: float = 10.0
    split_max_minutes: float = 20.0
    whisper_model: str = "large-v3-turbo"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_language: str = "tr"
    enable_censor: bool = True
    censor_words: list = field(default_factory=list)
    beep_freq_hz: int = 1000
    intro_path: str | None = None
    outro_path: str | None = None


DEFAULT_CENSOR_WORDS = [
    # Buraya istediğin küfürleri ekle. Kısmi eşleşme yapılır.
    # Örnek (yazılmadı; sen GUI'den eklersin).
]
