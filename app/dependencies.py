from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.database import DBSession
from app.models import Alumna
from app.services.administration import require_admin as _require_admin
from app.services.authentication import get_current_alumna
from app.settings import settings

CurrentAlumna = Annotated[Alumna, Depends(get_current_alumna)]


def require_admin_secret(
    x_admin_secret: Annotated[str | None, Header(alias="X-Admin-Secret")] = None,
) -> str:
    """Header-only authorization, for scripted access. The panel uses a cookie."""
    if not settings.admin_secret or x_admin_secret != settings.admin_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin credentials",
        )
    return x_admin_secret


AdminSecret = Annotated[str, Depends(require_admin_secret)]
# The dependency the admin routes actually use: cookie first, header as fallback.
Admin = Annotated[None, Depends(_require_admin)]

__all__ = ["Admin", "AdminSecret", "CurrentAlumna", "DBSession"]