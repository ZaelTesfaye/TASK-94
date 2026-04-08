"""Utility for creating anomaly alerts."""

from datetime import datetime, timezone

from src.models.base import db
from src.models.models import Alert
from src.models.enums import AlertSeverity, AlertStatus
from src.logging import logger


def create_alert(alert_type: str, severity: str, title: str, description: str = None, organization_id: str = None):
    """Persist an anomaly alert record.

    Args:
        alert_type: e.g. FAILED_LOGIN_SPIKE, BOOKING_CONFLICT_SPIKE, BACKUP_FAILURE
        severity: One of AlertSeverity values (LOW, MEDIUM, HIGH, CRITICAL)
        title: Short summary of the alert
        description: Detailed description
        organization_id: Optional org context
    """
    alert = Alert(
        alert_type=alert_type,
        severity=severity,
        status=AlertStatus.OPEN.value,
        title=title,
        description=description,
        organization_id=organization_id,
    )
    db.session.add(alert)
    db.session.commit()
    logger.info("alerts", "create", f"Alert created: type={alert_type} severity={severity}")
    return alert
