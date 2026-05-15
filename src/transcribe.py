"""faster-whisper ile Türkçe transkripsiyon (kelime zaman damgalı)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Word:
    text: str
    start: float
    end: float


_model_cache = {}


def get_model(name: str, device: str, compute_type: str):
    key = (name, device, compute_type)
    if key not in _model_cache:
        from faster_whisper import WhisperModel
        from .config import MODELS_DIR
        _model_cache[key] = WhisperModel(
            name,
            device=device,
            compute_type=compute_type,
            download_root=str(MODELS_DIR),
        )
    return _model_cache[key]


def transcribe(wav_path: Path, cfg, progress_cb=None) -> list[Word]:
    """Mikrofon wav'ini transkript et, kelime listesi döndür."""
    model = get_model(cfg.whisper_model, cfg.whisper_device, cfg.whisper_compute_type)

    segments, info = model.transcribe(
        str(wav_path),
        language=cfg.whisper_language,
        word_timestamps=True,
        vad_filter=True,
        beam_size=5,
    )

    words: list[Word] = []
    total_dur = info.duration or 0.0
    for seg in segments:
        if seg.words:
            for w in seg.words:
                words.append(Word(text=w.word.strip(), start=w.start, end=w.end))
        if progress_cb and total_dur > 0:
            progress_cb(min(1.0, seg.end / total_dur))
    return words
