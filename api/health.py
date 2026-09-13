from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/")
def root():
    return {
        "service": "ai-business-agent-starter-kit",
        "status": "running",
        "edition": "commercial-stage1",
    }


@router.get("/health")
def health():
    return {"ok": True}
