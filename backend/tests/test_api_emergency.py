from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db, ensure_schema
from app.main import app
from app.models.models import MarketDay, Pillar, Segment, Vendor


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    day = MarketDay(name="集日", day=date(2026, 9, 20))
    db.add(day); db.flush()
    seg = Segment(market_day_id=day.id, name="东街段", width_m=30.0,
                  start_emergency_m=1.0, end_emergency_m=1.0)
    db.add(seg); db.flush()
    db.add(Pillar(segment_id=seg.id, position_m=10.0, thickness_m=0.5, label="灯柱A"))
    db.add(Pillar(segment_id=seg.id, position_m=20.0, thickness_m=0.5, label="灯柱B"))
    for nm, w, pr in [("阿强烧烤", 4.0, 1), ("巨型舞台车", 12.0, 9)]:
        db.add(Vendor(market_day_id=day.id, name=nm, stall_width_m=w, priority=pr))
    db.commit(); db.close()

    def override_get_db():
        d = TestingSession()
        try:
            yield d
        finally:
            d.close()
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app), TestingSession
    app.dependency_overrides.clear()


def test_seed_listing_carries_emergency_values(client):
    c, _ = client
    rows = c.get("/api/segments").json()
    assert rows[0]["start_emergency_m"] == 1.0
    assert rows[0]["end_emergency_m"] == 1.0


def test_run_snapshot_uses_committed_values_and_diagram_matches_engine(client):
    c, _ = client
    d = c.post("/api/allocate/run?segment_id=1").json()
    # 第一摊后移到 1.0，摊内坐标全部在应急带内侧
    first = min(d["placements"], key=lambda p: p["start_m"])
    assert first["start_m"] == 1.0
    assert all(p["start_m"] >= 1.0 and p["end_m"] <= 29.0 for p in d["placements"])
    # 快照里的应急米数与登记一致，且就是引擎挖带口径
    assert d["emergency"] == {"start_m": 1.0, "end_m": 1.0}
    assert d["segment"]["start_emergency_m"] == 1.0
    ends = sorted(x for b in d["blocked_spans"] for x in (b["start_m"], b["end_m"]))
    assert ends[0] == 0.0 and ends[1] == 1.0 and ends[-1] == 30.0 and ends[-2] == 29.0
    # 巨型舞台车更容易进放不下
    names = {r["vendor_name"] for r in d["rejected"]}
    assert "巨型舞台车" in names


def test_update_then_rerun_recomputes_with_new_values(client):
    c, _ = client
    upd = c.put("/api/segments/1/emergency", json={"start_emergency_m": 3.0, "end_emergency_m": 2.0})
    assert upd.status_code == 200 and upd.json()["start_emergency_m"] == 3.0
    d = c.post("/api/allocate/run?segment_id=1").json()
    # 重算吃提交瞬间的新值：首摊起点=3，终点留白到 28
    assert min(p["start_m"] for p in d["placements"]) == 3.0
    assert d["emergency"] == {"start_m": 3.0, "end_m": 2.0}
    assert all(p["end_m"] <= 28.0 for p in d["placements"])
    # 刷新后街段页仍是新值
    assert c.get("/api/segments").json()[0]["end_emergency_m"] == 2.0


def test_invalid_values_reject_whole_order_and_everything_stays(client):
    c, Session = client
    for bad in [{"start_emergency_m": -1, "end_emergency_m": 1},
                {"start_emergency_m": 15, "end_emergency_m": 15},
                {"start_emergency_m": 30, "end_emergency_m": 0}]:
        r = c.put("/api/segments/1/emergency", json=bad)
        assert r.status_code == 400, r.text
    # 街段页停在改前 1/1
    seg = c.get("/api/segments").json()[0]
    assert (seg["start_emergency_m"], seg["end_emergency_m"]) == (1.0, 1.0)
    # 主图 / 放不下仍按改前运行边界（首摊仍在 1.0）
    d = c.get("/api/allocate/latest?segment_id=1").json()
    assert d["emergency"] == {"start_m": 1.0, "end_m": 1.0}
    assert min(p["start_m"] for p in d["placements"]) == 1.0
    db = Session()
    row = db.query(Segment).one()
    assert (row.start_emergency_m, row.end_emergency_m) == (1.0, 1.0)
    db.close()


def test_old_run_not_rewritten_by_new_values(client):
    c, _ = client
    old = c.post("/api/allocate/run?segment_id=1").json()
    old_id = old["id"]
    assert old["emergency"] == {"start_m": 1.0, "end_m": 1.0}
    assert c.put("/api/segments/1/emergency",
                 json={"start_emergency_m": 5.0, "end_emergency_m": 0.0}).status_code == 200
    c.post("/api/allocate/run?segment_id=1")  # 新运行
    # 点开旧运行：边界仍是 1/1 快照，不被新值改写
    replay = c.get(f"/api/allocate/runs/{old_id}").json()
    assert replay["emergency"] == {"start_m": 1.0, "end_m": 1.0}
    assert replay["placements"] == old["placements"]


def test_zero_zero_matches_no_band(client):
    c, _ = client
    assert c.put("/api/segments/1/emergency",
                 json={"start_emergency_m": 0.0, "end_emergency_m": 0.0}).status_code == 200
    d = c.post("/api/allocate/run?segment_id=1").json()
    # 与绿仓一致：无应急禁入块，首摊从 0 起挂
    assert d["emergency"] == {"start_m": 0.0, "end_m": 0.0}
    assert all(b["kind"] == "pillar" for b in d["blocked_spans"])
    assert min(p["start_m"] for p in d["placements"]) == 0.0


def test_ensure_schema_adds_columns_to_legacy_table(tmp_path):
    db_file = tmp_path / "legacy.db"
    eng = create_engine(f"sqlite:///{db_file}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE segments (id INTEGER PRIMARY KEY, market_day_id INTEGER, "
                          "name VARCHAR(64), width_m FLOAT)"))
        conn.execute(text("INSERT INTO segments (id, name, width_m) VALUES (1, '旧街段', 30.0)"))
    ensure_schema(eng)
    cols = {x["name"] for x in inspect(eng).get_columns("segments")}
    assert {"start_emergency_m", "end_emergency_m"} <= cols
