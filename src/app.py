from __future__ import annotations

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI

from presentation.summary_router import router as summary_router
from presentation.health_router import router as health_router
from presentation.predict_router import router as predict_router

load_dotenv()

app = FastAPI(title="HackathonIA API", version="1.0.0")
app.include_router(summary_router, prefix="/api")
app.include_router(health_router, prefix="/api")
app.include_router(predict_router, prefix="/api")


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)