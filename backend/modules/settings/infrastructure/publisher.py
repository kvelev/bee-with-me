"""Interim delivery of `SettingsChanged` to fire (until the outbox of step 4): ask the alarm service to re-evaluate."""
import logging

from ....fire import service as fire_service
from ..api import SettingsChanged

logger = logging.getLogger(__name__)


def publish(event: SettingsChanged) -> None:
    """Tell fire. The settings are already saved: a failure here is logged and never fails the request."""
    try:
        fire_service.service.request_evaluation()   # looked up at call time, so a test can replace it
    except Exception as exc:   # noqa: BLE001 - the save succeeded; the reaction must not turn it into a 500
        logger.error('settings: could not deliver %s: %s', type(event).__name__, exc)
