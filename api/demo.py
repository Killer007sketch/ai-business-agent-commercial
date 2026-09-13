from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(tags=["demo"])

_DEMO_FILE = Path(__file__).resolve().parent.parent / "demo" / "index.html"


@router.get("/demo", include_in_schema=False)
def demo_page():
    """Serve the self-contained browser demo shipped with the starter kit."""
    if not _DEMO_FILE.is_file():
        raise HTTPException(status_code=404, detail="Demo UI is not installed")
    return FileResponse(_DEMO_FILE, media_type="text/html")
