"""Commentary endpoints — AI macro analysis text.

GET  /commentary        → latest row (or generating/empty status)
POST /commentary/regenerate → sync generate (caller waits), returns new row
"""

from fastapi import APIRouter

from backend.app.core import commentary
from backend.app.schemas.commentary import Commentary

router = APIRouter(prefix="/commentary", tags=["commentary"])


@router.get("", response_model=Commentary)
def get_commentary():
    """Latest AI commentary (or status=generating/empty)."""
    return Commentary(**commentary.get_current())


@router.post("/regenerate", response_model=Commentary)
def regenerate():
    """Re-run the model on current data (sync). Returns the new commentary."""
    return Commentary(**commentary.generate(blocking=True))
