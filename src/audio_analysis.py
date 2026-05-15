"""Mikrofon ses kanalını çıkar ve sessiz segmentleri tespit et."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Segment:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def count_audio_streams(video_path: Path) -> int:
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index",
        "-of", "csv=p=0",
        str(video_path),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return len([l for l in out.stdout.strip().splitlines() if l.strip()])


def extract_mic_track(video_path: Path, mic_track_index: int, out_wav: Path) -> Path:
    """OBS multi-track MKV'den mikrofon kanalını mono 16kHz wav olarak çıkar.

    FFmpeg track indeksleri 0-bazlı; OBS UI'da Track 1/2 ise burada 0/1.
    """
    n = count_audio_streams(video_path)
    if mic_track_index >= n:
        raise RuntimeError(
            f"Bu video {n} ses kanalı içeriyor (sen track {mic_track_index} istedin).\n\n"
            f"OBS multi-track kaydı yapılmamış görünüyor. Kontrol et:\n"
            f"  1) OBS → Settings → Output → Output Mode: Advanced olmalı\n"
            f"  2) Recording sekmesinde Audio Track 1 ve 2 tikli olmalı\n"
            f"  3) Advanced Audio Properties'te mic Track 2'ye, oyun sesi Track 1'e atanmalı\n\n"
            f"Tek track varsa GUI'de 'Mikrofon track indeksi'ni 0 yap "
            f"(ama o zaman oyun sesi de mic'e karışır)."
        )
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-map", f"0:a:{mic_track_index}",
        "-ac", "1",
        "-ar", "16000",
        "-vn",
        "-f", "wav",
        str(out_wav),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg mic çıkarımı başarısız:\n{result.stderr[-2000:]}")
    return out_wav


def load_wav_mono(wav_path: Path) -> tuple[np.ndarray, int]:
    """16-bit PCM wav'i numpy float32 [-1, 1] olarak yükle."""
    import wave

    with wave.open(str(wav_path), "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return data, sr


def _moving_average(x: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return x
    kernel = np.ones(window, dtype=np.float32) / window
    return np.convolve(x, kernel, mode="same")


def detect_silence(
    samples: np.ndarray,
    sample_rate: int,
    threshold_db: float = -42.0,
    min_silence: float = 0.9,
    frame_ms: float = 20.0,
    smooth_ms: float = 150.0,
    hysteresis_db: float = 6.0,
) -> list[Segment]:
    """Sessiz segmentleri (start, end saniye) döndür.

    Yumuşatma + histerezis ile konuşma içindeki kısa dB çukurları sessizlik sayılmaz.

    threshold_db: bu eşiğin altına düşüp `min_silence` süresince orada kalan kısımlar sessiz sayılır.
    hysteresis_db: konuşma içinde sayılmaya devam etmek için (threshold + hysteresis) dB üstüne çıkmak yeterli.
    smooth_ms: RMS eğrisinin yumuşatma penceresi.
    """
    frame_len = int(sample_rate * frame_ms / 1000)
    if frame_len <= 0:
        raise ValueError("frame_ms çok küçük")

    n_frames = len(samples) // frame_len
    if n_frames == 0:
        return []

    trimmed = samples[: n_frames * frame_len].reshape(n_frames, frame_len)
    rms = np.sqrt(np.mean(trimmed ** 2, axis=1) + 1e-12)
    db = 20.0 * np.log10(rms + 1e-12)

    smooth_frames = max(1, int(smooth_ms / frame_ms))
    db_smooth = _moving_average(db, smooth_frames)

    # Histerezis: silence_th düşük, voice_th yüksek
    silence_th = threshold_db
    voice_th = threshold_db + hysteresis_db

    state_silent = True
    silent_frames = np.zeros(n_frames, dtype=bool)
    for i in range(n_frames):
        if state_silent:
            if db_smooth[i] >= voice_th:
                state_silent = False
        else:
            if db_smooth[i] < silence_th:
                state_silent = True
        silent_frames[i] = state_silent

    silences: list[Segment] = []
    frame_sec = frame_ms / 1000.0
    i = 0
    while i < n_frames:
        if silent_frames[i]:
            j = i
            while j < n_frames and silent_frames[j]:
                j += 1
            start = i * frame_sec
            end = j * frame_sec
            if end - start >= min_silence:
                silences.append(Segment(start, end))
            i = j
        else:
            i += 1
    return silences


def dump_debug_csv(
    out_csv: Path,
    silences: list[Segment],
    keep: list[Segment],
) -> None:
    import csv
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["type", "start_sec", "end_sec", "duration_sec"])
        for s in silences:
            w.writerow(["SILENCE", f"{s.start:.3f}", f"{s.end:.3f}", f"{s.duration:.3f}"])
        for k in keep:
            w.writerow(["KEEP", f"{k.start:.3f}", f"{k.end:.3f}", f"{k.duration:.3f}"])


def invert_silences(
    silences: list[Segment],
    total_duration: float,
    pad_before: float = 0.15,
    pad_after: float = 0.20,
) -> list[Segment]:
    """Sessiz aralıkları verince, *tutulacak* konuşma segmentlerini döndür.

    Konuşma kenarlarına padding eklenir (kelime başı/sonu kesilmesin diye).
    """
    keep: list[Segment] = []
    cursor = 0.0
    for s in silences:
        # Sessizliği kısalt: başına pad_before, sonuna pad_after bırak (konuşma için)
        effective_start = max(cursor, s.start + pad_before)
        if effective_start > cursor + 0.01:
            keep.append(Segment(cursor, effective_start))
        cursor = max(cursor, s.end - pad_after)
        if cursor < 0:
            cursor = 0
    if cursor < total_duration - 0.01:
        keep.append(Segment(cursor, total_duration))

    # Çok kısa parçaları at (jump cut için en az 100ms olsun)
    return [seg for seg in keep if seg.duration >= 0.1]


def get_duration(video_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def analyze(video_path: Path, cfg) -> tuple[list[Segment], float]:
    """Tam analiz: mic çıkar, sessizlik bul, tutulacak segmentleri döndür."""
    from .config import TEMP_DIR

    wav = TEMP_DIR / f"{video_path.stem}_mic.wav"
    extract_mic_track(video_path, cfg.mic_track_index, wav)
    samples, sr = load_wav_mono(wav)
    silences = detect_silence(
        samples, sr,
        threshold_db=cfg.silence_threshold_db,
        min_silence=cfg.min_silence_duration,
    )
    total = get_duration(video_path)
    keep = invert_silences(silences, total, cfg.padding_before, cfg.padding_after)

    # Debug CSV: çıktıyı analiz etmek için
    debug_csv = TEMP_DIR / f"{video_path.stem}_segments.csv"
    dump_debug_csv(debug_csv, silences, keep)

    return keep, total
