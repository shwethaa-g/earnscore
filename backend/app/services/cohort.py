"""Cohort seasonality indices (city x work type), learned from every worker's weekly series in the database."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import CohortSeasonality, User, WeeklySeries, WorkerProfile, utcnow
from app.scoring.engine import cohort_index_from


def recompute(db: Session, city: str | None = None, work_type: str | None = None) -> dict:
    q = select(WorkerProfile.user_id, WorkerProfile.city, WorkerProfile.work_type).join(User).where(User.role == "worker")
    if city:
        q = q.where(WorkerProfile.city == city)
    if work_type:
        q = q.where(WorkerProfile.work_type == work_type)
    members: dict[tuple[str, str], list[int]] = defaultdict(list)
    for uid, c, wt in db.execute(q).all():
        if c and wt:
            members[(c, wt)].append(uid)
    out = {}
    for (c, wt), uids in members.items():
        series = defaultdict(lambda: ([], []))
        for uid, week, earned in db.execute(select(WeeklySeries.user_id, WeeklySeries.week, WeeklySeries.earned)
                                            .where(WeeklySeries.user_id.in_(uids)).order_by(WeeklySeries.week)).all():
            series[uid][0].append(week)
            series[uid][1].append(earned)
        index, n = cohort_index_from(list(series.values()))
        db.execute(delete(CohortSeasonality).where(CohortSeasonality.city == c, CohortSeasonality.work_type == wt))
        now = utcnow()
        db.add_all([CohortSeasonality(city=c, work_type=wt, week_of_year=k, index=v, n_workers=n, updated_at=now)
                    for k, v in index.items()])
        out[f"{c}/{wt}"] = n
    db.flush()
    return out
