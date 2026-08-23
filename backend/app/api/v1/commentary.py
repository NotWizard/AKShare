"""Commentary endpoints — AI macro analysis text.

GET  /commentary        → latest row (or generating/empty status)
POST /commentary/regenerate → sync generate (caller waits), returns new row.
    Token-guarded (F4): it spends money on a paid LLM call, and any page the
    user browsed could previously fire it with
    ``fetch(…, {method:'POST', mode:'no-cors'})`` — a billing attack that needs
    no response body, so CORS never blocked it.
"""

from fastapi import APIRouter, Depends

from backend.app.core import commentary
from backend.app.core.auth import require_token
from backend.app.schemas.commentary import Commentary

router = APIRouter(prefix="/commentary", tags=["commentary"])


@router.get("", response_model=Commentary)
def get_commentary():
    """Latest AI commentary (or status=generating/empty)."""
    return Commentary(**commentary.get_current())


@router.post("/regenerate", response_model=Commentary,
             dependencies=[Depends(require_token)])
def regenerate():
    """Re-run the model on current data (sync). Returns the new commentary."""
    return Commentary(**commentary.generate(blocking=True))
