from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def ensure_schema(eng=None) -> None:
    """create_all 只建新表；给已存在的 segments 表补应急带列（旧库升级）。"""
    eng = eng or engine
    inspector = inspect(eng)
    if "segments" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("segments")}
    with eng.begin() as conn:
        if "start_emergency_m" not in existing:
            conn.execute(text("ALTER TABLE segments ADD COLUMN start_emergency_m FLOAT DEFAULT 0.0"))
        if "end_emergency_m" not in existing:
            conn.execute(text("ALTER TABLE segments ADD COLUMN end_emergency_m FLOAT DEFAULT 0.0"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
