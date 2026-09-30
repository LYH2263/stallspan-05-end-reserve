"""1D First-Fit stall placement along a street segment.

两端应急带与挡柱同属禁入区间：先在同一套 blocked 区间里挖两端应急、再并入挡柱
（重叠即合并，重叠区仍是禁入），可用开间由合并后的禁入区间统一取补得到。
摊位只允许落在 free span 内，带内不得出现任何摊位起止。
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, field

KIND_PILLAR = "pillar"
KIND_START_EMERGENCY = "start_emergency"
KIND_END_EMERGENCY = "end_emergency"

REASON_EMERGENCY = "应急带占用"
REASON_GAP = "无连续空档可放下且不跨越挡柱"

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
class BlockedSpan:
    start_m: float
    end_m: float
    kinds: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)

@dataclass
class AllocResult:
    placements: list[Placement]
    rejected: list[Rejected]
    free_spans: list[tuple[float, float]]
    blocked_spans: list[BlockedSpan] = field(default_factory=list)
    start_emergency_m: float = 0.0
    end_emergency_m: float = 0.0

def _merge_blocked(raw: list[tuple[float, float, str, str]]) -> list[BlockedSpan]:
    """raw: (lo, hi, kind, label)；相接/重叠即合并为同一禁入区间，种类与标签并入。"""
    raw = [r for r in raw if r[1] - r[0] > 1e-9]
    raw.sort(key=lambda r: (r[0], r[1]))
    merged: list[BlockedSpan] = []
    for lo, hi, kind, label in raw:
        if not merged or lo > merged[-1].end_m + 1e-9:
            merged.append(BlockedSpan(round(lo, 3), round(hi, 3), [kind], [label]))
        else:
            last = merged[-1]
            last.end_m = round(max(last.end_m, hi), 3)
            if kind not in last.kinds:
                last.kinds.append(kind)
            if label not in last.labels:
                last.labels.append(label)
    return merged

def blocked_intervals(width_m: float, pillars: list[dict],
                      start_emergency_m: float = 0.0,
                      end_emergency_m: float = 0.0) -> list[BlockedSpan]:
    """应急带与挡柱进同一个 blocked 列表一次合并；重叠区并入禁入，不另算一套。"""
    raw: list[tuple[float, float, str, str]] = []
    start_em = max(0.0, float(start_emergency_m or 0.0))
    end_em = max(0.0, float(end_emergency_m or 0.0))
    if start_em > 0:
        raw.append((0.0, min(width_m, start_em), KIND_START_EMERGENCY, "起点应急带"))
    if end_em > 0:
        raw.append((max(0.0, width_m - end_em), width_m, KIND_END_EMERGENCY, "终点应急带"))
    for p in pillars:
        half = p.get("thickness_m", 0.4) / 2.0
        lo = max(0.0, p["position_m"] - half)
        hi = min(width_m, p["position_m"] + half)
        if hi > lo:
            raw.append((lo, hi, KIND_PILLAR, p.get("label") or "挡柱"))
    return _merge_blocked(raw)

def _free_from_blocked(width_m: float, blocked: list[BlockedSpan]) -> list[tuple[float, float]]:
    spans = []
    cursor = 0.0
    for b in blocked:
        if b.start_m > cursor:
            spans.append((cursor, b.start_m))
        cursor = b.end_m
    if cursor < width_m:
        spans.append((cursor, width_m))
    return [(round(a, 3), round(b, 3)) for a, b in spans if b - a > 1e-6]

def free_spans_from_pillars(width_m: float, pillars: list[dict],
                            start_emergency_m: float = 0.0,
                            end_emergency_m: float = 0.0) -> list[tuple[float, float]]:
    """可用开间：先挖两端应急，挡柱在同一套禁入里合并，再统一取补。"""
    blocked = blocked_intervals(width_m, pillars, start_emergency_m, end_emergency_m)
    return _free_from_blocked(width_m, blocked)

def blocked_label(b: BlockedSpan) -> str:
    has_pillar = KIND_PILLAR in b.kinds
    has_em = bool({KIND_START_EMERGENCY, KIND_END_EMERGENCY} & set(b.kinds))
    if has_pillar:
        pillar_labels = [lbl for lbl in b.labels
                         if lbl not in ("起点应急带", "终点应急带")] or ["挡柱"]
        return "、".join(pillar_labels) + ("·应急" if has_em else "")
    return "、".join(b.labels)

def _first_fit(width_m: float, vendors: list[dict], pillars: list[dict],
               start_emergency_m: float, end_emergency_m: float):
    """单次 first-fit。返回 (blocked, remain, placements, rejected_ids)。"""
    blocked = blocked_intervals(width_m, pillars, start_emergency_m, end_emergency_m)
    remain = [[a, b] for a, b in _free_from_blocked(width_m, blocked)]
    ordered = sorted(vendors, key=lambda v: (v.get("priority", 1), v["id"]))
    placements: list[Placement] = []
    rejected_ids: list[int] = []
    for v in ordered:
        need = float(v["stall_width_m"])
        for span in remain:
            avail = span[1] - span[0]
            if avail + 1e-9 >= need:
                start = span[0]
                end = start + need
                placements.append(Placement(v["id"], v["name"], round(start, 3), round(end, 3), need))
                span[0] = end
                break
        else:
            rejected_ids.append(v["id"])
    return blocked, remain, placements, rejected_ids

def allocate_first_fit(width_m: float, vendors: list[dict], pillars: list[dict],
                       start_emergency_m: float = 0.0,
                       end_emergency_m: float = 0.0) -> AllocResult:
    """vendors sorted by priority ascending then id; each needs stall_width_m contiguous
    in one free span. 应急带与挡柱同属禁入，摊位起止不得落入带内。

    放不下原因以「应急 0 的同摊同序裸跑」为对照：裸跑放得下、挖带后放不下，才是
    应急带占用；裸跑也放不下才是空档长度不够/跨柱，两种原因各自独立成句。
    """
    se = max(0.0, float(start_emergency_m or 0.0))
    ee = max(0.0, float(end_emergency_m or 0.0))
    blocked, remain, placements, rejected_ids = _first_fit(width_m, vendors, pillars, se, ee)
    bare_placed_ids: set[int] = set()
    if se > 0 or ee > 0:
        _, _, bare_placements, _ = _first_fit(width_m, vendors, pillars, 0.0, 0.0)
        bare_placed_ids = {p.vendor_id for p in bare_placements}
    by_id = {v["id"]: v for v in vendors}
    rejected: list[Rejected] = []
    for vid in rejected_ids:
        v = by_id[vid]
        need = float(v["stall_width_m"])
        # 宽度其实够、只是可用开间被应急带挤掉（含起止本会落在带内）→ 应急带占用；
        # 裸跑同样放不下才是空档长度不够，绝不改写成跨柱或与空档原因并句
        reason = REASON_EMERGENCY if vid in bare_placed_ids else REASON_GAP
        rejected.append(Rejected(vid, v["name"], need, reason))
    free = [(round(a, 3), round(b, 3)) for a, b in remain if b - a > 1e-6]
    return AllocResult(placements, rejected, free, blocked, round(se, 3), round(ee, 3))

def result_to_dict(r: AllocResult) -> dict:
    return {
        "placements": [asdict(p) for p in r.placements],
        "rejected": [asdict(x) for x in r.rejected],
        "free_spans": [{"start_m": a, "end_m": b} for a, b in r.free_spans],
        "blocked_spans": [{"start_m": b.start_m, "end_m": b.end_m,
                           "kinds": list(b.kinds), "label": blocked_label(b)}
                          for b in r.blocked_spans],
        "start_emergency_m": r.start_emergency_m,
        "end_emergency_m": r.end_emergency_m,
    }
