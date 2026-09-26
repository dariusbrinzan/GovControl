from typing import Literal

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import async_session_factory

router = APIRouter()


@router.get("/health")
async def health() -> dict[Literal["status"], Literal["ok"]]:
    """Report whether the API process is running."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness() -> dict[Literal["status"], Literal["ready"]]:
    """Report whether the API can communicate with its required persistence services."""
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
    return {"status": "ready"}
