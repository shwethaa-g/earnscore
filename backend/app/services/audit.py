import logging

from sqlalchemy.orm import Session

from app.models import AuditLog

log = logging.getLogger("earnscore.audit")


def audit(db: Session, actor_id: int | None, action: str, target_type: str = "", target_id: object = "",
          details: dict | None = None, ip: str = "") -> AuditLog:
    entry = AuditLog(actor_id=actor_id, action=action, target_type=target_type, target_id=str(target_id),
                     details=details or {}, ip=ip)
    db.add(entry)
    db.flush()
    log.info("audit", extra={"action": action, "actor": actor_id, "target": f"{target_type}:{target_id}"})
    return entry
