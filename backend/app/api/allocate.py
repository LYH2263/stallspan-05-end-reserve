import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import AllocationRun, Pillar, Segment, Vendor
from app.services.first_fit_engine import (
    allocate_first_fit, blocked_intervals, blocked_label, result_to_dict,
)
router = APIRouter(prefix="/allocate", tags=["allocate"])

def _run_now(seg: Segment, pillars: list[dict], vendors: list[dict]) -> dict:
    """按提交瞬间的应急值现算——登记改完后再确认必须吃新值。"""
    result = result_to_dict(allocate_first_fit(
        seg.width_m, vendors, pillars,
        seg.start_emergency_m or 0.0, seg.end_emergency_m or 0.0))
    result["segment"] = {"id": seg.id, "name": seg.name, "width_m": seg.width_m,
                         "start_emergency_m": seg.start_emergency_m or 0.0,
                         "end_emergency_m": seg.end_emergency_m or 0.0}
    result["pillars"] = pillars
    return result

@router.post("/run")
def run_allocate(segment_id: int = 1, db: Session = Depends(get_db)):
    seg = db.get(Segment, segment_id)
    if not seg: raise HTTPException(404, "街段不存在")
    pillars = [{"position_m": p.position_m, "thickness_m": p.thickness_m, "label": p.label}
               for p in db.scalars(select(Pillar).where(Pillar.segment_id == segment_id)
                                   .order_by(Pillar.position_m)).all()]
    vendors = [{"id": v.id, "name": v.name, "stall_width_m": v.stall_width_m, "priority": v.priority}
               for v in db.scalars(select(Vendor).where(Vendor.market_day_id == seg.market_day_id)).all()]
    result = _run_now(seg, pillars, vendors)
    run = AllocationRun(segment_id=segment_id, created_at=datetime.utcnow(),
                        result_json=json.dumps(result, ensure_ascii=False))
    db.add(run); db.commit(); db.refresh(run)
    return {"id": run.id, **result}

def _from_snapshot(run: AllocationRun) -> dict:
    """旧 run 只按它自己存下的挡柱补渲染区间，应急固定为快照值，绝不读当前段新值。"""
    data = json.loads(run.result_json)
    data.setdefault("start_emergency_m", 0.0)
    data.setdefault("end_emergency_m", 0.0)
    if isinstance(data.get("segment"), dict):
        data["segment"].setdefault("start_emergency_m", data["start_emergency_m"])
        data["segment"].setdefault("end_emergency_m", data["end_emergency_m"])
    if "blocked_spans" not in data:
        # 旧快照：当时尚无应急带概念，按应急 0 与快照内挡柱补一套，边界不被新值改写
        width = data["segment"]["width_m"]
        blocked = blocked_intervals(width, data.get("pillars", []), 0.0, 0.0)
        data["blocked_spans"] = [
            {"start_m": b.start_m, "end_m": b.end_m, "kinds": list(b.kinds),
             "label": blocked_label(b)}
            for b in blocked]
    return {"id": run.id, **data}

@router.get("/latest")
def latest(segment_id: int = 1, db: Session = Depends(get_db)):
    run = db.scalars(select(AllocationRun).where(AllocationRun.segment_id == segment_id)
                     .order_by(AllocationRun.id.desc())).first()
    if not run:
        return run_allocate(segment_id=segment_id, db=db)
    return _from_snapshot(run)

@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(AllocationRun, run_id)
    if not run: raise HTTPException(404, "运行不存在")
    return _from_snapshot(run)
