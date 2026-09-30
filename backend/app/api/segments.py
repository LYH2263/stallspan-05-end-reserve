import math
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Segment
router = APIRouter(prefix="/segments", tags=["segments"])

def _to_dict(r: Segment) -> dict:
    return {"id": r.id, "market_day_id": r.market_day_id, "name": r.name, "width_m": r.width_m,
            "start_emergency_m": r.start_emergency_m or 0.0,
            "end_emergency_m": r.end_emergency_m or 0.0}

class EmergencyUpdate(BaseModel):
    start_emergency_m: float
    end_emergency_m: float

@router.get("")
def list_segments(db: Session = Depends(get_db)):
    return [_to_dict(r) for r in db.scalars(select(Segment).order_by(Segment.id)).all()]

@router.put("/{segment_id}/emergency")
def update_emergency(segment_id: int, body: EmergencyUpdate, db: Session = Depends(get_db)):
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    s, e = body.start_emergency_m, body.end_emergency_m
    # 非法值（负数或两端应急之和不小于街宽）整单拒绝：库与任何展示都停在改前
    if not (math.isfinite(s) and math.isfinite(e)) or s < 0 or e < 0:
        raise HTTPException(400, "应急米数须为不小于 0 的有限数")
    if s + e >= seg.width_m:
        raise HTTPException(400, "两端应急米数之和必须小于街宽")
    seg.start_emergency_m = s
    seg.end_emergency_m = e
    db.commit()
    db.refresh(seg)
    return _to_dict(seg)
