from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import admin, auth, officer, worker
from app.core.db import get_db
from app.core.deps import current_user
from app.ingest import aa
from app.models import Lender, User
from app.schemas import CITIES, WORK_TYPES

router = APIRouter()
router.include_router(auth.router)
router.include_router(worker.router)
router.include_router(officer.router)
router.include_router(admin.router)


@router.get("/meta", tags=["meta"])
def meta():
    return {"cities": CITIES, "work_types": WORK_TYPES, "languages": ["en", "ta", "hi"], "aa": aa.status()}


@router.get("/meta/lenders", tags=["meta"])
def lenders(_: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Lender).where(Lender.is_active.is_(True)).order_by(Lender.name)).all()
    return {"lenders": [{"id": l.id, "name": l.name, "default_tenure_weeks": l.default_tenure_weeks,
                         "annual_rate": l.annual_rate, "grievance_email": l.grievance_email} for l in rows]}
