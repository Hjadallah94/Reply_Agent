from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from reply_agent.api.auth import router as auth_router
from reply_agent.api.dashboard import router as dashboard_router
from reply_agent.api.knowledge import router as knowledge_router
from reply_agent.api.meta_compliance import router as meta_compliance_router
from reply_agent.api.onboarding import router as onboarding_router
from reply_agent.api.orders import router as orders_router
from reply_agent.channels.instagram.webhook import router as instagram_router
from reply_agent.channels.messenger.webhook import router as messenger_router
from reply_agent.channels.whatsapp.webhook import router as whatsapp_router
from reply_agent.config import get_settings

app = FastAPI(title="Reply Agent")
app.add_middleware(SessionMiddleware, secret_key=get_settings().session_secret_key)
app.include_router(whatsapp_router)
app.include_router(instagram_router)
app.include_router(messenger_router)
app.include_router(knowledge_router)
app.include_router(orders_router)
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(onboarding_router)
app.include_router(meta_compliance_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
