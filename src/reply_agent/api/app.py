from fastapi import FastAPI

from reply_agent.api.knowledge import router as knowledge_router
from reply_agent.channels.whatsapp.webhook import router as whatsapp_router

app = FastAPI(title="Reply Agent")
app.include_router(whatsapp_router)
app.include_router(knowledge_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
