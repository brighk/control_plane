import logging
import os
import secrets

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("CONTROL_PLANE_DB", "sqlite:///control_plane.db")

# Private key the server uses to SSH into hosts for shutdown.
SSH_KEY_PATH = os.environ.get("CONTROL_PLANE_SSH_KEY")

# archer-monitor's Prometheus endpoint, e.g. http://127.0.0.1:9105/metrics.
# Unset: the Network section is hidden.
ARCHER_METRICS_URL = os.environ.get("CONTROL_PLANE_ARCHER_METRICS_URL") or None

# Signs the session cookie. Set it in production, or every restart logs everyone out.
SECRET_KEY = os.environ.get("CONTROL_PLANE_SECRET_KEY") or ""
if not SECRET_KEY:
    SECRET_KEY = secrets.token_urlsafe(32)
    logger.warning(
        "CONTROL_PLANE_SECRET_KEY is not set; using a random key. "
        "Sessions will not survive a restart."
    )
