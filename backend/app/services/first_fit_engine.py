"""1D First-Fit stall placement along a street segment.

禁入区只有一套：两端应急带 [0, start_emergency_m] 与
[width-end_emergency_m, width] 先挖空，再与挡柱区间取并集合并。
可用开间（free spans）一律从应急带内侧起算，带内不得出现任何摊位起止。
放不下原因严格二选一：应急带占用 / 空档长度不够且不可跨越挡柱，不并句。
"""
from __future__ import annotations
from dataclasses import asdict, dataclass

REASON_EMERGENCY = "应急带占用"
REASON_GAP = "空档长度不够且不可跨越挡柱"

@dataclass
class Placement:
    vendor_id: int
    vendor_name: str
    start_m: float
    end_m: float
    width_m: float

@dataclass
class Rejected:
    vendor_id: int
    vendor_name: str
    width_m: float
    reason: str

@dataclass
class AllocResult:
    placements: list[Placement]
    rejected: list[Rejected]
    free_spans: list[tuple[float, float]]
    blocked_spans: list[dict]
    start_emergency_m: float
    end_emergency_m: float

def _pillar_intervals(width_m: float, pillars: list[dict]) -> list[tuple[float, float]]:
    out = []
    for p in pillars:
        half = p.get("thickness_m", 0.4) / 2.0
        lo = max(0.0, p["position_m"] - half)
        hi = min(width_m, p["position_m"] + half)
        if hi > lo:
            out.append((lo, hi))
    return out

def _merge_blocked(intervals: list[tuple[float, float, str]]) -> list[dict]:
    """intervals: (lo, hi, source)；合并重叠，source 记录各段来自哪些禁入源。"""
    intervals = sorted(intervals, key=lambda x: x[0])
    merged: list[dict] = []
    for lo, hi, source in intervals:
        if not merged or lo > merged[-1]["end_m"]:
            merged.append({"start_m": lo, "end_m": hi, "sources": {source}})
        else:
            merged[-1]["end_m"] = max(merged[-1]["end_m"], hi)
            merged[-1]["sources"].add(source)
    out = []
    for m in merged:
        # 应急带与挡柱厚度重叠时，重叠区并入禁入；画面上重叠区按挡柱禁入块呈现
        kind = "pillar" if "pillar" in m["sources"] else "emergency"
        out.append({"start_m": round(m["start_m"], 3), "end_m": round(m["end_m"], 3), "kind": kind})
    return out

def blocked_and_free_spans(
    width_m: float,
    pillars: list[dict],
    start_emergency_m: float = 0.0,
    end_emergency_m: float = 0.0,
) -> tuple[list[dict], list[tuple[float, float]]]:
    """先挖两端应急带，再并入挡柱，返回 (合并后的禁入区, 可用开间)。二者恰好分割 [0, width]。"""
    intervals: list[tuple[float, float, str]] = []
    if start_emergency_m > 0:
        intervals.append((0.0, min(start_emergency_m, width_m), "emergency"))
    if end_emergency_m > 0:
        intervals.append((max(0.0, width_m - end_emergency_m), width_m, "emergency"))
    for lo, hi in _pillar_intervals(width_m, pillars):
        intervals.append((lo, hi, "pillar"))
    blocked = _merge_blocked(intervals)
    spans: list[tuple[float, float]] = []
    cursor = 0.0
    for b in blocked:
        if b["start_m"] > cursor:
            spans.append((cursor, b["start_m"]))
        cursor = b["end_m"]
    if cursor < width_m:
        spans.append((cursor, width_m))
    free = [(round(a, 3), round(b, 3)) for a, b in spans if b - a > 1e-6]
    return blocked, free

def free_spans_from_pillars(width_m: float, pillars: list[dict]) -> list[tuple[float, float]]:
    """无应急带时的可用开间（绿仓口径）。"""
    _, free = blocked_and_free_spans(width_m, pillars, 0.0, 0.0)
    return free

def allocate_first_fit(
    width_m: float,
    vendors: list[dict],
    pillars: list[dict],
    start_emergency_m: float = 0.0,
    end_emergency_m: float = 0.0,
) -> AllocResult:
    """vendors 按 priority 再 id 排序；每个摊位需在同一段可用开间内连续放下。

    落位顺序：先挖两端应急带，再按挡柱切空，全程只有一套禁入区间。
    """
    blocked, spans = blocked_and_free_spans(width_m, pillars, start_emergency_m, end_emergency_m)
    # 对照口径：仅有挡柱（不挖应急带）时的开间，用于判定放不下的真正原因
    _, spans_no_emergency = blocked_and_free_spans(width_m, pillars, 0.0, 0.0)
    remain = [[a, b] for a, b in spans]
    remain_no_emergency = [[a, b] for a, b in spans_no_emergency]
    ordered = sorted(vendors, key=lambda v: (v.get("priority", 1), v["id"]))
    placements: list[Placement] = []
    rejected: list[Rejected] = []
    for v in ordered:
        need = float(v["stall_width_m"])
        # 先在"无应急带"对照队列里判定本摊位此刻是否放得下（先于本摊任何消耗）
        fits_without_band = any((b - a) + 1e-9 >= need for a, b in remain_no_emergency)
        placed = False
        for span in remain:
            avail = span[1] - span[0]
            if avail + 1e-9 >= need:
                start = span[0]
                end = start + need
                placements.append(Placement(v["id"], v["name"], round(start, 3), round(end, 3), need))
                span[0] = end
                placed = True
                break
        if not placed:
            # 宽度其实够、只是起止会落在应急带内（含被带挤碎）→ 应急带占用；
            # 撤掉应急带、同一排队顺序下仍放不下 → 空档长度不够。两句不并写。
            reason = REASON_EMERGENCY if fits_without_band else REASON_GAP
            rejected.append(Rejected(v["id"], v["name"], need, reason))
        # 对照队列始终同步尝试本摊位（实际被拒者在无带世界里可能本可放下、须占位）
        for span in remain_no_emergency:
            if (span[1] - span[0]) + 1e-9 >= need:
                span[0] += need
                break
    free = [(round(a, 3), round(b, 3)) for a, b in remain if b - a > 1e-6]
    return AllocResult(placements, rejected, free, blocked,
                       float(start_emergency_m), float(end_emergency_m))

def result_to_dict(r: AllocResult) -> dict:
    return {
        "placements": [asdict(p) for p in r.placements],
        "rejected": [asdict(x) for x in r.rejected],
        "free_spans": [{"start_m": a, "end_m": b} for a, b in r.free_spans],
        "blocked_spans": r.blocked_spans,
        "emergency": {"start_m": r.start_emergency_m, "end_m": r.end_emergency_m},
    }
