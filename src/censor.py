"""Küfür listesine göre kelime zaman damgalarını yakala ve bip aralıkları üret."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .transcribe import Word


@dataclass
class CensorInterval:
    start: float
    end: float


def _normalize(s: str) -> str:
    # Türkçe karakterleri ASCII'ye, küçült, noktalama at
    table = str.maketrans("ÇĞİıÖŞÜçğıöşü", "CGIIOSUcgiosu")
    s = s.translate(table).lower()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def find_censor_intervals(
    words: list[Word],
    bad_words: list[str],
    pad: float = 0.05,
) -> list[CensorInterval]:
    """Küfür kelimelerini/öbeklerini transkriptte bulup zaman aralıklarını döndür.

    - Tek kelime ("sik") → alt-dize ile eşleşir ("siktir", "sikim").
    - Öbek ("amına koyim") → ardışık kelimelerle eşleşir, her parça alt-dize ile.
    """
    if not bad_words:
        return []

    # bad listesini tek-kelimelik ve öbek olarak ayır
    singles: list[str] = []
    phrases: list[list[str]] = []
    for b in bad_words:
        b = b.strip()
        if not b:
            continue
        parts = [_normalize(p) for p in b.split() if p.strip()]
        parts = [p for p in parts if p]
        if not parts:
            continue
        if len(parts) == 1:
            singles.append(parts[0])
        else:
            phrases.append(parts)

    intervals: list[CensorInterval] = []
    nwords = [_normalize(w.text) for w in words]

    # Tek kelimeler
    for idx, nw in enumerate(nwords):
        if not nw:
            continue
        for bad in singles:
            if bad in nw:
                w = words[idx]
                intervals.append(CensorInterval(
                    start=max(0.0, w.start - pad),
                    end=w.end + pad,
                ))
                break

    # Öbekler: ardışık eşleşme
    for phrase in phrases:
        L = len(phrase)
        for i in range(len(nwords) - L + 1):
            ok = True
            for k, p in enumerate(phrase):
                if not nwords[i + k] or p not in nwords[i + k]:
                    ok = False
                    break
            if ok:
                start = words[i].start
                end = words[i + L - 1].end
                intervals.append(CensorInterval(
                    start=max(0.0, start - pad),
                    end=end + pad,
                ))

    return merge_intervals(intervals)


def merge_intervals(intervals: list[CensorInterval]) -> list[CensorInterval]:
    if not intervals:
        return []
    intervals = sorted(intervals, key=lambda x: x.start)
    merged = [intervals[0]]
    for cur in intervals[1:]:
        last = merged[-1]
        if cur.start <= last.end + 0.05:
            last.end = max(last.end, cur.end)
        else:
            merged.append(cur)
    return merged


def build_beep_filter(intervals: list[CensorInterval], beep_freq: int = 1000) -> str:
    """FFmpeg filter_complex stringi: orijinal sesi sansürlü aralıklarda susturup
    aynı aralıklarda sinüs bip sesi mix eder.

    Kullanım: ffmpeg -i input.mkv -filter_complex <STR> -map "[aout]" -map 0:v -c:v copy out.mkv
    """
    if not intervals:
        return ""

    # Mic'i sansür aralıklarında sustur (enable=interval içinde iken volume=0 uygula)
    interval_exprs = "+".join(
        f"between(t,{i.start:.3f},{i.end:.3f})" for i in intervals
    )
    mute = f"[0:a]volume=enable='{interval_exprs}':volume=0[muted]"

    # Bip sesi: sürekli sinüs üret, kıs (0.3'e), sonra aralık DIŞINDA sustur
    max_end = max(i.end for i in intervals) + 1.0
    beep_gen = f"sine=frequency={beep_freq}:duration={max_end:.3f},volume=0.3[bquiet]"
    # not(...) → aralık dışında 1 (uygulanır → volume=0), aralık içinde 0 (uygulanmaz → ses var)
    beep_gate = f"[bquiet]volume=enable='not({interval_exprs})':volume=0[beep]"
    mix = "[muted][beep]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"

    return ";".join([mute, beep_gen, beep_gate, mix])
