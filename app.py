from fastapi import FastAPI

from api.conversations import router as conversations_router
from api.health import router as health_router
from api.opportunities import router as opportunities_router
from api.proposals import router as proposals_router
from api.webhooks import router as webhooks_router
from database.base import Base
from database.session import engine
from models import conversation as conversation_models  # noqa: F401
from models import opportunity as opportunity_models  # noqa: F401

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Business Agent Starter Kit",
    description=(
        "Developer starter kit for opportunity filtering, proposal generation, "
        "conversation handling, risk gating, and optional email automation."
    ),
    version="1.0.0-rc1",
)

app.include_router(health_router)
app.include_router(opportunities_router)
app.include_router(proposals_router)
app.include_router(conversations_router)
app.include_router(webhooks_router)
