from fastapi import FastAPI

from api.health import router as health_router
from api.opportunities import router as opportunities_router
from api.proposals import router as proposals_router
from database.base import Base
from database.session import engine

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Business Agent Starter Kit",
    version="1.0.0-stage3",
)

app.include_router(health_router)
app.include_router(opportunities_router)
app.include_router(proposals_router)
