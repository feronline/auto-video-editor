"""Ana boru hattı: input → analiz → (sansür) → kes → parçala → intro/outro."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .audio_analysis import analyze, extract_mic_track
from .censor import build_beep_filter, find_censor_intervals
from .config import OUTPUT_DIR, TEMP_DIR, EditConfig
from .transcribe import transcribe
from .video_processor import (
    concat_with_intro_outro,
    cut_silences,
    prepare_audio,
    split_by_duration,
)


def run_pipeline(
    video_path: Path,
    cfg: EditConfig,
    log: Callable[[str], None] = print,
    progress: Callable[[float, str], None] = lambda p, s: None,
) -> list[Path]:
    """Tüm akışı çalıştır, üretilen parça yollarını döndür."""
    video_path = Path(video_path)
    stem = video_path.stem
    work_dir = TEMP_DIR / stem
    work_dir.mkdir(parents=True, exist_ok=True)

    # --- 1) Sansür için transkript (gerekirse) → beep filter
    beep_filter = ""
    if cfg.enable_censor and cfg.censor_words:
        log("Mikrofon kanalı çıkarılıyor (transkripsiyon için)...")
        progress(0.05, "Mic çıkarılıyor")
        mic_wav = work_dir / "mic.wav"
        extract_mic_track(video_path, cfg.mic_track_index, mic_wav)

        log("Transkripsiyon başlıyor (Whisper large-v3-turbo, Türkçe)...")
        progress(0.10, "Transkript")
        words = transcribe(mic_wav, cfg, progress_cb=lambda p: progress(0.10 + p * 0.40, "Transkript"))
        log(f"  {len(words)} kelime transkript edildi.")

        intervals = find_censor_intervals(words, cfg.censor_words)
        log(f"  {len(intervals)} sansür aralığı bulundu.")

        if intervals:
            beep_filter = build_beep_filter(intervals, cfg.beep_freq_hz)

    # --- 2) Ses hazırlığı: (sansürlü?) mic + oyun sesi mix → tek ses kanallı video
    log("Ses kanalları hazırlanıyor (mic + oyun sesi mix)...")
    progress(0.55, "Ses mix")
    prepared = work_dir / "prepared.mkv"
    prepare_audio(
        video_path,
        mic_track=cfg.mic_track_index,
        game_track=cfg.game_track_index,
        include_game=cfg.include_game_audio,
        out_path=prepared,
        beep_filter=beep_filter,
        game_gain=cfg.game_audio_gain,
    )
    source_for_cut = prepared

    # --- 3) Sessizlik analizi: SADECE saf mic'e bakar (oyun sesi karışmasın)
    log("Sessizlik aralıkları tespit ediliyor (saf mic üzerinden)...")
    progress(0.62, "Sessizlik analizi")
    from .audio_analysis import (
        detect_silence, dump_debug_csv, get_duration, invert_silences,
        load_wav_mono,
    )
    # Saf mic WAV gerekli — sansür branch'inde zaten çıkardık, yoksa şimdi çıkar
    mic_wav_for_silence = work_dir / "mic.wav"
    if not mic_wav_for_silence.exists():
        extract_mic_track(video_path, cfg.mic_track_index, mic_wav_for_silence)
    samples, sr = load_wav_mono(mic_wav_for_silence)
    silences = detect_silence(
        samples, sr,
        threshold_db=cfg.silence_threshold_db,
        min_silence=cfg.min_silence_duration,
    )
    total_dur = get_duration(source_for_cut)
    keep = invert_silences(silences, total_dur, cfg.padding_before, cfg.padding_after)
    dump_debug_csv(work_dir / "segments.csv", silences, keep)
    kept_sec = sum(s.duration for s in keep)
    log(f"  Toplam: {total_dur:.1f}s → Tutulacak: {kept_sec:.1f}s "
        f"(%{kept_sec/total_dur*100:.1f}), {len(keep)} parça.")

    # --- 3) Kesim
    log("Sessizler kesiliyor, parçalar birleştiriliyor...")
    progress(0.65, "Kesim")
    cut_path = work_dir / "cut.mp4"
    cut_silences(source_for_cut, keep, cut_path)

    # --- 4) Parçalama (opsiyonel)
    parts_dir = OUTPUT_DIR / stem
    parts_dir.mkdir(parents=True, exist_ok=True)
    if cfg.split_enabled:
        log(f"~{cfg.target_clip_minutes:.0f} dakikalık parçalara bölünüyor...")
        progress(0.85, "Parçalama")
        parts = split_by_duration(
            cut_path, parts_dir,
            min_minutes=cfg.split_min_minutes,
            max_minutes=cfg.split_max_minutes,
            target_minutes=cfg.target_clip_minutes,
        )
        log(f"  {len(parts)} parça oluştu.")
    else:
        log("Parçalama kapalı — tek dosya olarak çıkarılıyor.")
        progress(0.85, "Tek dosya")
        import shutil
        single = parts_dir / f"{stem}_edited.mp4"
        shutil.move(str(cut_path), str(single))
        parts = [single]

    # --- 5) Intro/outro
    intro = Path(cfg.intro_path) if cfg.intro_path else None
    outro = Path(cfg.outro_path) if cfg.outro_path else None
    if intro or outro:
        log("Intro/outro ekleniyor...")
        progress(0.92, "Intro/Outro")
        finals: list[Path] = []
        for i, p in enumerate(parts, 1):
            final = parts_dir / f"{stem}_final_part{i:02d}.mp4"
            concat_with_intro_outro(p, final, intro, outro)
            finals.append(final)
        parts = finals

    progress(1.0, "Bitti")
    log(f"Tamamlandı: {len(parts)} parça → {parts_dir}")
    return parts
