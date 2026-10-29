from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import SessionDep

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Check the service is running",
    responses={503: {"description": "The service is up but cannot reach the database."}},
)
async def health(session: SessionDep, response: Response) -> dict[str, str]:
    """Returns `200 {"status": "ok"}` when the service and database are both reachable."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "database": "unreachable"}
    return {"status": "ok", "database": "ok"}
