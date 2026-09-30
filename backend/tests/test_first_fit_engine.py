from app.services.first_fit_engine import (
    REASON_EMERGENCY, REASON_GAP, allocate_first_fit, blocked_and_free_spans, free_spans_from_pillars,
)

PILLARS_SEED = [{"position_m": 10.0, "thickness_m": 0.5}, {"position_m": 20.0, "thickness_m": 0.5}]
VENDORS_SEED = [
    {"id": 1, "name": "阿强烧烤", "stall_width_m": 4.0, "priority": 1},
    {"id": 2, "name": "林记糖水", "stall_width_m": 3.0, "priority": 1},
    {"id": 3, "name": "老周水果", "stall_width_m": 5.0, "priority": 2},
    {"id": 4, "name": "小美饰品", "stall_width_m": 2.5, "priority": 2},
    {"id": 5, "name": "大碗面", "stall_width_m": 6.0, "priority": 1},
    {"id": 6, "name": "手作皮具", "stall_width_m": 3.5, "priority": 3},
    {"id": 7, "name": "巨型舞台车", "stall_width_m": 12.0, "priority": 9},
]

def test_free_spans_with_pillars():
    spans = free_spans_from_pillars(30.0, PILLARS_SEED)
    assert len(spans) == 3
    assert spans[0][0] == 0.0

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
    r = allocate_first_fit(30.0, vendors, PILLARS_SEED)
    assert len(r.rejected) == 1
    assert r.rejected[0].vendor_name == "Huge"

def test_zero_bands_identical_to_green_warehouse():
    """均为 0 时与绿仓一致：开间、落位、原因完全相同。"""
    a = allocate_first_fit(30.0, VENDORS_SEED, PILLARS_SEED, 0.0, 0.0)
    b = allocate_first_fit(30.0, VENDORS_SEED, PILLARS_SEED)
    assert [(p.start_m, p.end_m) for p in a.placements] == [(p.start_m, p.end_m) for p in b.placements]
    assert free_spans_from_pillars(30.0, PILLARS_SEED) == [(0.0, 9.75), (10.25, 19.75), (20.25, 30.0)]
    assert a.free_spans == b.free_spans
    assert a.blocked_spans == [
        {"start_m": 9.75, "end_m": 10.25, "kind": "pillar"},
        {"start_m": 19.75, "end_m": 20.25, "kind": "pillar"},
    ]

def test_seed_bands_first_stall_shifts_and_total_shrinks():
    """种子东街段 1/1：第一摊后移到 1.0；总可放 30-2=28 再扣柱 1 → 27m，比无带短 2m。"""
    blocked, spans = blocked_and_free_spans(30.0, PILLARS_SEED, 1.0, 1.0)
    assert spans == [(1.0, 9.75), (10.25, 19.75), (20.25, 29.0)]
    assert sum(b - a for a, b in spans) == 27.0
    kinds = [(b["start_m"], b["end_m"], b["kind"]) for b in blocked]
    assert kinds[0] == (0.0, 1.0, "emergency")
    assert kinds[-1] == (29.0, 30.0, "emergency")
    # 禁入区与可用开间恰好分割整条街，只有一套空隙
    cuts = {0.0, 30.0}
    for b in blocked:
        cuts.add(b["start_m"]); cuts.add(b["end_m"])
    for a, b2 in spans:
        cuts.add(a); cuts.add(b2)
    assert sorted(cuts) == [0, 1, 9.75, 10.25, 19.75, 20.25, 29, 30]

    r = allocate_first_fit(30.0, VENDORS_SEED, PILLARS_SEED, 1.0, 1.0)
    first = min(r.placements, key=lambda p: p.start_m)
    assert first.start_m == 1.0 and first.vendor_name == "阿强烧烤"
    # 带内不得出现任何摊位起止
    for p in r.placements:
        assert p.start_m >= 1.0 - 1e-9 and p.end_m <= 29.0 + 1e-9
    # 巨型舞台车在更短的开间下进放不下
    giant = next(x for x in r.rejected if x.vendor_name == "巨型舞台车")
    assert giant.width_m == 12.0

def test_reason_emergency_when_width_actually_fits():
    """宽度其实够（25<=30）但起止必落在带内 → 应急带占用；无柱可跨，不得改写成跨柱。"""
    vendors = [{"id": 1, "name": "长条", "stall_width_m": 25.0, "priority": 1}]
    r = allocate_first_fit(30.0, vendors, [], start_emergency_m=10.0, end_emergency_m=0.0)
    assert len(r.rejected) == 1
    assert r.rejected[0].reason == REASON_EMERGENCY
    assert "挡柱" not in r.rejected[0].reason and "空档" not in r.rejected[0].reason

def test_reason_gap_never_mentions_emergency():
    """撤掉应急带仍放不下（20m 摊、柱切两半）→ 空档长度不够且不可跨越挡柱，不并句应急带。"""
    vendors = [{"id": 1, "name": "巨无霸", "stall_width_m": 20.0, "priority": 1}]
    pillars = [{"position_m": 15.0, "thickness_m": 1.0}]
    r = allocate_first_fit(30.0, vendors, pillars, start_emergency_m=1.0, end_emergency_m=1.0)
    assert len(r.rejected) == 1
    assert r.rejected[0].reason == REASON_GAP
    assert "应急" not in r.rejected[0].reason

def test_end_band_blocks_fit_at_tail():
    vendors = [{"id": 1, "name": "尾摊", "stall_width_m": 29.0, "priority": 1}]
    r = allocate_first_fit(30.0, vendors, [], 0.0, 2.0)  # 仅剩 28m
    assert len(r.rejected) == 1
    assert r.rejected[0].reason == REASON_EMERGENCY
    assert r.free_spans == [(0.0, 28.0)]

def test_band_pillar_overlap_merges_into_one_blocked_set():
    """应急带与挡柱厚度重叠：重叠区并入禁入，只按一套空隙切，不允许柱、带各算一套。"""
    # 柱区间 [0,2] 与起点应急 [0,2] 完全重叠
    blocked, spans = blocked_and_free_spans(10.0, [{"position_m": 1.0, "thickness_m": 2.0}], 2.0, 0.0)
    assert blocked == [{"start_m": 0.0, "end_m": 2.0, "kind": "pillar"}]
    assert spans == [(2.0, 10.0)]
    # 部分重叠：柱 [1.5,3.5] 与带 [0,2] → 合并 [0,3.5] 一段
    blocked2, spans2 = blocked_and_free_spans(10.0, [{"position_m": 2.5, "thickness_m": 2.0}], 2.0, 0.0)
    assert blocked2 == [{"start_m": 0.0, "end_m": 3.5, "kind": "pillar"}]
    assert spans2 == [(3.5, 10.0)]
    # 落位起点在合并后的禁入区内侧
    r = allocate_first_fit(10.0, [{"id": 1, "name": "A", "stall_width_m": 3.0, "priority": 1}],
                           [{"position_m": 2.5, "thickness_m": 2.0}], 2.0, 0.0)
    assert r.placements[0].start_m == 3.5

def test_emergency_displaces_later_vendor_reason():
    """带内不可放进放不下时写应急带占用；本来就能放下的摊主被带挤掉也算应急带，不与空档并句。"""
    vendors = [
        {"id": 1, "name": "首摊", "stall_width_m": 7.0, "priority": 1},
        {"id": 2, "name": "两米摊", "stall_width_m": 2.0, "priority": 2},
    ]
    # 街宽 10、起点应急 2 → 仅剩 [2,10] 共 8m。
    # 首摊占 7 后余 1m，两米摊放不下；无带对照下 10-7=3m 本可放下 → 应急带占用
    r = allocate_first_fit(10.0, vendors, [], start_emergency_m=2.0, end_emergency_m=0.0)
    assert [p.vendor_name for p in r.placements] == ["首摊"]
    assert r.placements[0].start_m == 2.0
    assert len(r.rejected) == 1
    assert r.rejected[0].vendor_name == "两米摊"
    assert r.rejected[0].reason == REASON_EMERGENCY

def test_counterfactual_rejected_vendor_takes_space():
    """高优先摊主在带世界被拒，但在无带世界本可放下并占位——须影响后续摊主的原因判定。"""
    vendors = [
        {"id": 1, "name": "九米摊", "stall_width_m": 9.0, "priority": 1},
        {"id": 2, "name": "次摊", "stall_width_m": 1.0, "priority": 2},
    ]
    # 街宽 10、起点应急 2 → 开间仅 8m，九米摊带世界放不下（无带 10m 可放 → 应急带占用），
    # 无带世界它占 [0,9]，次摊仍可放 [9,10]；带世界余 8m 次摊放得下。
    r = allocate_first_fit(10.0, vendors, [], start_emergency_m=2.0, end_emergency_m=0.0)
    rej = {x.vendor_name: x.reason for x in r.rejected}
    assert rej == {"九米摊": REASON_EMERGENCY}
    assert [p.vendor_name for p in r.placements] == ["次摊"]
