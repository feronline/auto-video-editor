"""Video kesme, birleştirme, parçalama, intro/outro ekleme — FFmpeg ile."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .audio_analysis import Segment


def _run(cmd: list[str]) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(
            f"FFmpeg hatası:\n  cmd: {' '.join(cmd[:6])}...\n  stderr:\n{res.stderr[-2000:]}"
        )


def build_keep_filter(keep: list[Segment]) -> tuple[str, str]:
    """Birden çok keep segmentini tek geçişte birleştiren filter_complex üret."""
    v_parts, a_parts = [], []
    for i, seg in enumerate(keep):
        v_parts.append(
            f"[0:v]trim=start={seg.start:.3f}:end={seg.end:.3f},setpts=PTS-STARTPTS[v{i}]"
        )
        a_parts.append(
            f"[0:a]atrim=start={seg.start:.3f}:end={seg.end:.3f},asetpts=PTS-STARTPTS[a{i}]"
        )
    concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(len(keep)))
    concat = f"{concat_inputs}concat=n={len(keep)}:v=1:a=1[vout][aout]"
    chain = ";".join(v_parts + a_parts + [concat])
    return chain, "[vout]", "[aout]"  # type: ignore[return-value]


def cut_silences(
    video_path: Path,
    keep: list[Segment],
    out_path: Path,
    censor_filter: str = "",
    batch_size: int = 80,
) -> Path:
    """Sessizleri at, kalanları birleştir.

    Çok fazla segment varsa (yüzlerce) tek geçişte ffmpeg patlar — bu yüzden
    batch'ler halinde kesip sonra concat ediyoruz.
    """
    if not keep:
        raise ValueError("Tutulacak segment yok!")
    if censor_filter:
        raise ValueError("Sansür filtresi cut_silences içine değil, ön-pass'e verilir.")

    if len(keep) <= batch_size:
        return _cut_batch(video_path, keep, out_path)

    # Batch'lere böl, ara MP4'ler üret, sonra demuxer concat ile birleştir
    work = out_path.parent / f"_cut_{out_path.stem}"
    work.mkdir(parents=True, exist_ok=True)
    batch_files: list[Path] = []
    for bi in range(0, len(keep), batch_size):
        chunk = keep[bi : bi + batch_size]
        bf = work / f"batch_{bi:04d}.mp4"
        _cut_batch(video_path, chunk, bf)
        batch_files.append(bf)

    concat_list = work / "concat.txt"
    with concat_list.open("w", encoding="utf-8") as f:
        for bf in batch_files:
            f.write(f"file '{bf.as_posix()}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(out_path),
    ]
    _run(cmd)
    return out_path


def _cut_batch(video_path: Path, keep: list[Segment], out_path: Path) -> Path:
    """Tek bir batch için filter_complex kesim + concat. Filter dosyaya yazılır
    (Windows komut satırı uzunluk limitini aşmamak için).
    """
    chain, vmap, amap = build_keep_filter(keep)
    filter_file = out_path.with_suffix(".filter.txt")
    filter_file.write_text(chain, encoding="utf-8")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-/filter_complex", str(filter_file),
        "-map", vmap, "-map", amap,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        str(out_path),
    ]
    _run(cmd)
    return out_path


def apply_censor(
    video_path: Path,
    censor_filter: str,
    out_path: Path,
    mic_track_index: int = 1,
) -> Path:
    """Mikrofon kanalına bip uygula. Video kopyalanır, sadece ses re-encode.

    Çıktıda tek ses kanalı kalır (sansürlenmiş mic).
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-map", "0:v",
        "-filter_complex", censor_filter.replace("[0:a]", f"[0:a:{mic_track_index}]"),
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        str(out_path),
    ]
    _run(cmd)
    return out_path


def prepare_audio(
    video_path: Path,
    mic_track: int,
    game_track: int,
    include_game: bool,
    out_path: Path,
    beep_filter: str = "",
    game_gain: float = 1.0,
) -> Path:
    """Sansür (varsa) uygula + mic ile oyun sesini mix et + video'yu kopyala.

    Çıktı: video + TEK ses kanalı (mix). Sessizlik kesimi için ideal.
    """
    from .audio_analysis import count_audio_streams
    n = count_audio_streams(video_path)
    if mic_track >= n:
        raise RuntimeError(
            f"Bu video {n} ses kanalı içeriyor (mic={mic_track} istendi). "
            f"OBS multi-track ayarını kontrol et."
        )

    has_game = include_game and game_track < n and game_track != mic_track

    # Mic zinciri: ya bip filtresi (mic'e uygulanır) ya da düz mic
    if beep_filter:
        # build_beep_filter [0:a]'yı kullanır ve [aout] üretir → mic track'ine yönlendir, isim çakışmasın
        mic_chain = beep_filter.replace("[0:a]", f"[0:a:{mic_track}]").replace("[aout]", "[micx]")
    else:
        mic_chain = f"[0:a:{mic_track}]anull[micx]"

    if has_game:
        game_chain = f"[0:a:{game_track}]volume={game_gain:.3f}[gamex]"
        mix = "[gamex][micx]amix=inputs=2:duration=longest:normalize=0[aout]"
        filter_str = ";".join([mic_chain, game_chain, mix])
    else:
        # Tek track (mic) çıkışı
        filter_str = mic_chain.replace("[micx]", "[aout]")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-filter_complex", filter_str,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        str(out_path),
    ]
    _run(cmd)
    return out_path


def remux_to_single_audio(video_path: Path, mic_track_index: int, out_path: Path) -> Path:
    """Multi-track video'yu tek ses kanallı (sadece mic) hale getir."""
    from .audio_analysis import count_audio_streams
    n = count_audio_streams(video_path)
    if mic_track_index >= n:
        raise RuntimeError(
            f"Bu video {n} ses kanalı içeriyor (sen track {mic_track_index} istedin).\n\n"
            f"OBS multi-track kaydı yapılmamış. Düzeltmek için:\n"
            f"  1) OBS → Settings → Output → 'Output Mode' = Advanced (Simple DEĞİL!)\n"
            f"  2) Recording sekmesinde Audio Track 1 VE 2 tikli\n"
            f"  3) Advanced Audio Properties: mic Track 2'ye, oyun sesi Track 1'e\n\n"
            f"Hızlı test için GUI'de 'Mikrofon track indeksi'ni 0 yap "
            f"(oyun sesi mic'e karışır)."
        )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-map", "0:v",
        "-map", f"0:a:{mic_track_index}",
        "-c:v", "copy",
        "-c:a", "copy",
        str(out_path),
    ]
    _run(cmd)
    return out_path


def split_by_duration(
    video_path: Path,
    out_dir: Path,
    min_minutes: float = 10.0,
    max_minutes: float = 20.0,
    target_minutes: float = 15.0,
) -> list[Path]:
    """Videoyu target_minutes parçalara böl. Son parça min'in altına düşerse
    bir önceki parçayla birleştir.
    """
    from .audio_analysis import get_duration

    out_dir.mkdir(parents=True, exist_ok=True)
    total = get_duration(video_path)
    target_sec = target_minutes * 60
    min_sec = min_minutes * 60

    # Kesim noktaları
    splits: list[tuple[float, float]] = []
    cursor = 0.0
    while cursor < total:
        end = min(cursor + target_sec, total)
        if total - end < min_sec and total - end > 0:
            end = total
        splits.append((cursor, end))
        cursor = end

    outputs: list[Path] = []
    for i, (s, e) in enumerate(splits, 1):
        op = out_dir / f"{video_path.stem}_part{i:02d}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{s:.3f}",
            "-to", f"{e:.3f}",
            "-i", str(video_path),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            str(op),
        ]
        _run(cmd)
        outputs.append(op)
    return outputs


def concat_with_intro_outro(
    main: Path,
    out_path: Path,
    intro: Path | None = None,
    outro: Path | None = None,
) -> Path:
    """Intro + main + outro birleştir. Tüm girdiler aynı codec/çözünürlükte
    değilse re-encode ile uyumlu hale getirilir.
    """
    parts: list[Path] = []
    if intro and intro.exists():
        parts.append(intro)
    parts.append(main)
    if outro and outro.exists():
        parts.append(outro)

    if len(parts) == 1:
        shutil.copy(main, out_path)
        return out_path

    # Re-encode ile concat (concat filter), uyumsuzluk problemini önler
    inputs: list[str] = []
    for p in parts:
        inputs += ["-i", str(p)]
    n = len(parts)
    chain_parts = []
    for i in range(n):
        chain_parts.append(f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
                           f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=60[v{i}]")
        chain_parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
    concat_in = "".join(f"[v{i}][a{i}]" for i in range(n))
    chain_parts.append(f"{concat_in}concat=n={n}:v=1:a=1[vout][aout]")
    chain = ";".join(chain_parts)

    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", chain,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        str(out_path),
    ]
    _run(cmd)
    return out_path
