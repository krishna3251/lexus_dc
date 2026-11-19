from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from stats_store import server_stats
import os
import hmac
from core.environment import load_environment

load_environment()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
@app.head("/")
def root():
    return {"status": "ok"}


@app.get("/stats")
def get_stats(x_api_key: str | None = Header(None)):
    # Missing configuration must never silently expose private service statistics.
    api_key = os.getenv("API_SECRET_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="Statistics access is not configured")
    if not x_api_key or not hmac.compare_digest(x_api_key.encode("utf-8"), api_key.encode("utf-8")):
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return server_stats

@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/ready")
def readiness():
    is_ready = getattr(app.state, "bot_readiness", None)
    if is_ready is None or not is_ready():
        raise HTTPException(status_code=503, detail="Discord bot is not ready")
    return {"status": "ready"}
