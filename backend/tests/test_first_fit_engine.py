from app.services.first_fit_engine import (
    KIND_END_EMERGENCY, KIND_PILLAR, KIND_START_EMERGENCY,
    REASON_EMERGENCY, REASON_GAP,
    allocate_first_fit, free_spans_from_pillars, blocked_intervals,
)

PILLARS = [{"position_m": 10.0, "thickness_m": 0.5}, {"position_m": 20.0, "thickness_m": 0.5}]

def test_free_spans_with_pillars():
    spans = free_spans_from_pillars(30.0, PILLARS)
    assert len(spans) == 3
    assert spans[0][0] == 0.0

def test_zero_emergency_matches_green_warehouse():
    """均为 0 时与绿仓（无应急）逐字段一致。"""
    vendors = [
        {"id": 1, "name": "A", "stall_width_m": 4.0, "priority": 1},
        {"id": 2, "name": "B", "stall_width_m": 12.0, "priority": 1},
    ]
    r = allocate_first_fit(30.0, vendors, PILLARS, 0.0, 0.0)
    assert r.start_emergency_m == 0.0 and r.end_emergency_m == 0.0
    # 无应急禁入，挡柱之外全部可用
    assert all(KIND_PILLAR in b.kinds and len(b.kinds) == 1 for b in r.blocked_spans)
    assert free_spans_from_pillars(30.0, PILLARS, 0.0, 0.0) == free_spans_from_pillars(30.0, PILLARS)
    # 没有应急带时第一摊从 0 起挂
    assert min(p.start_m for p in r.placements) == 0.0
    assert len(r.placements) + len(r.rejected) == 2
    assert all(x.reason == REASON_GAP for x in r.rejected)

def test_first_fit_no_cross_pillar():
    vendors = [
        {"id": 1, "name": "A", "stall_width_m": 4.0, "priority": 1},
        {"id": 2, "name": "B", "stall_width_m": 12.0, "priority": 1},
    ]
    pillars = [{"position_m": 10.0, "thickness_m": 0.5}]
    r = allocate_first_fit(30.0, vendors, pillars)
    assert any(p.vendor_name == "A" for p in r.placements)
    assert len(r.placements) + len(r.rejected) == 2

def test_reject_oversized():
    vendors = [{"id": 1, "name": "Huge", "stall_width_m": 25.0, "priority": 1}]
    r = allocate_first_fit(30.0, vendors, PILLARS)
    assert len(r.rejected) == 1
    assert r.rejected[0].vendor_name == "Huge"

def test_emergency_bands_carve_ends_and_shorten_usable():
    """种子布局：起点应急 1、终点应急 1 后第一摊必须后移，总可放变短。"""
    vendors = [
        {"id": 1, "name": "阿强烧烤", "stall_width_m": 4.0, "priority": 1},
        {"id": 2, "name": "林记糖水", "stall_width_m": 3.0, "priority": 1},
        {"id": 3, "name": "大碗面", "stall_width_m": 6.0, "priority": 1},
    ]
    bare = allocate_first_fit(30.0, vendors, PILLARS)
    dug = allocate_first_fit(30.0, vendors, PILLARS, 1.0, 1.0)
    first = sorted(dug.placements, key=lambda p: p.start_m)[0]
    # 第一摊从应急带内侧起挂，带内不得出现任何摊位起止
    assert first.start_m >= 1.0 - 1e-9
    assert all(p.start_m >= 1.0 - 1e-9 and p.end_m <= 29.0 + 1e-9 for p in dug.placements)
    # 总可放变短：可放区间合计长度 = 30 - 挡柱 1.0 - 应急 2.0
    usable = sum(b - a for a, b in free_spans_from_pillars(30.0, PILLARS, 1.0, 1.0))
    assert abs(usable - 27.0) < 1e-6
    bare_usable = sum(b - a for a, b in free_spans_from_pillars(30.0, PILLARS))
    assert bare_usable - usable == 2.0
    # 两端确实被挖成禁入，且米数与登记一致
    kinds = {(b.start_m, b.end_m): b.kinds for b in dug.blocked_spans}
    assert kinds[(0.0, 1.0)] == [KIND_START_EMERGENCY]
    assert kinds[(29.0, 30.0)] == [KIND_END_EMERGENCY]

def test_emergency_overlaps_pillar_merges_single_blocked():
    """应急带与挡柱厚度重叠时并入同一禁入区间，不另算一套空隙。"""
    # 起点应急 10.2 盖住左柱 9.75–10.25 的左半 → 合并为 0–10.25
    blocked = blocked_intervals(30.0, PILLARS, 10.2, 0.0)
    head = blocked[0]
    assert (head.start_m, head.end_m) == (0.0, 10.25)
    assert KIND_START_EMERGENCY in head.kinds and KIND_PILLAR in head.kinds
    # 合并后只取一套补集：首空档从 10.25 开始，不会再出现 9.75/10.2 两套起点
    spans = free_spans_from_pillars(30.0, PILLARS, 10.2, 0.0)
    assert spans[0][0] == 10.25

def test_giant_stage_truck_reasons_differ():
    """巨型舞台车：无应急放不下=空档长度不够；1/1 挖带后仍放不下但无应急本可放=应急带占用。"""
    truck = [{"id": 1, "name": "巨型舞台车", "stall_width_m": 12.0, "priority": 9}]
    # 仅挡柱时 20.25–30 有 9.75，0–9.75 有 9.75，12 放不下 → 空档原因
    bare = allocate_first_fit(30.0, truck, PILLARS)
    assert len(bare.rejected) == 1 and bare.rejected[0].reason == REASON_GAP
    # 换成一段无挡柱的长街：12 在 30m 内本可放下，挖 10m 起点应急后只剩 20m 仍可放；
    # 挖 19m 时剩余 11m 放不下，而裸跑放得下 → 应急带占用，且原因独立成句
    no_pillars = []
    fits_bare = allocate_first_fit(30.0, truck, no_pillars)
    assert len(fits_bare.placements) == 1
    squeezed = allocate_first_fit(30.0, truck, no_pillars, 19.0, 0.0)
    assert len(squeezed.rejected) == 1
    assert squeezed.rejected[0].reason == REASON_EMERGENCY
    assert REASON_GAP not in squeezed.rejected[0].reason
    # 宽度其实够但起止会落在带内（22m 摊、起点带 10m）也判应急带占用，不改写跨柱
    wide = [{"id": 2, "name": "长大篷", "stall_width_m": 22.0, "priority": 1}]
    r = allocate_first_fit(30.0, wide, no_pillars, 10.0, 0.0)
    assert r.rejected[0].reason == REASON_EMERGENCY
