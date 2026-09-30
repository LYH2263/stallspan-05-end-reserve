from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Segment
router = APIRouter(prefix="/segments", tags=["segments"])

def segment_dict(r: Segment) -> dict:
    return {"id": r.id, "market_day_id": r.market_day_id, "name": r.name,
            "width_m": r.width_m,
            "start_emergency_m": r.start_emergency_m or 0.0,
            "end_emergency_m": r.end_emergency_m or 0.0}

@router.get("")
def list_segments(db: Session = Depends(get_db)):
    return [segment_dict(r) for r in db.scalars(select(Segment).order_by(Segment.id)).all()]

class EmergencyUpdate(BaseModel):
    start_emergency_m: float
    end_emergency_m: float

@router.put("/{segment_id}/emergency")
def update_emergency(segment_id: int, body: EmergencyUpdate, db: Session = Depends(get_db)):
    """整单校验：负数或两端应急之和不小于街宽一律拒绝，库与各页停在改前。"""
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    start_em = body.start_emergency_m
    end_em = body.end_emergency_m
    # 拒绝 NaN/Inf
    if not (start_em == start_em and end_em == end_em) or start_em in (float("inf"), float("-inf")) \
            or end_em in (float("inf"), float("-inf")):
        raise HTTPException(400, "应急米数非法")
    if start_em < 0 or end_em < 0:
        raise HTTPException(400, "应急米数不得为负")
    if start_em + end_em >= seg.width_m:
        raise HTTPException(400, "两端应急米数之和必须小于街宽")
    seg.start_emergency_m = start_em
    seg.end_emergency_m = end_em
    db.commit()
    db.refresh(seg)
    return segment_dict(seg)
