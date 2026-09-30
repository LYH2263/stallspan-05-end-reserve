import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import AllocationRun, Pillar, Segment, Vendor
from app.services.first_fit_engine import allocate_first_fit, result_to_dict
router = APIRouter(prefix="/allocate", tags=["allocate"])

def _compute(seg: Segment, pillars: list[dict], vendors: list[dict]) -> dict:
    start_band = seg.start_emergency_m or 0.0
    end_band = seg.end_emergency_m or 0.0
    # 现算口径：使用提交瞬间街段上的新应急值，禁止吃改前可用区间
    result = result_to_dict(allocate_first_fit(
        seg.width_m, vendors, pillars, start_band, end_band))
    result["segment"] = {"id": seg.id, "name": seg.name, "width_m": seg.width_m,
                         "start_emergency_m": start_band, "end_emergency_m": end_band}
    result["pillars"] = pillars
    return result

@router.post("/run")
def run_allocate(segment_id: int = 1, db: Session = Depends(get_db)):
    seg = db.get(Segment, segment_id)
    if not seg: raise HTTPException(404, "街段不存在")
    pillars = [{"position_m": p.position_m, "thickness_m": p.thickness_m,
                "label": p.label}
               for p in db.scalars(select(Pillar).where(Pillar.segment_id == segment_id)).all()]
    vendors = [{"id": v.id, "name": v.name, "stall_width_m": v.stall_width_m, "priority": v.priority}
               for v in db.scalars(select(Vendor).where(Vendor.market_day_id == seg.market_day_id)).all()]
    result = _compute(seg, pillars, vendors)
    run = AllocationRun(segment_id=segment_id, created_at=datetime.utcnow(),
                        result_json=json.dumps(result, ensure_ascii=False))
    db.add(run); db.commit(); db.refresh(run)
    return {"id": run.id, **result}

@router.get("/latest")
def latest(segment_id: int = 1, db: Session = Depends(get_db)):
    run = db.scalars(select(AllocationRun).where(AllocationRun.segment_id == segment_id)
                     .order_by(AllocationRun.id.desc())).first()
    if not run:
        return run_allocate(segment_id=segment_id, db=db)
    # 旧运行完整展示其落库瞬间的快照：新应急值不改写其边界
    data = json.loads(run.result_json)
    return {"id": run.id, **data}

@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(AllocationRun, run_id)
    if not run:
        raise HTTPException(404, "运行不存在")
    # 始终回放该运行落库时的快照（含当时的应急值与边界），不按街段现值重算
    data = json.loads(run.result_json)
    return {"id": run.id, **data}
