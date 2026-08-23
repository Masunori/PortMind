"""Local canonical-demo reset endpoint."""

from fastapi import APIRouter

from app.seed import seed

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.post("/reset")
def reset_demo() -> dict[str, str]:
    """Reconstruct the complete deterministic demo dataset."""

    seed()
    return {"status": "reset"}
