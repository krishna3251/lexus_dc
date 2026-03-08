from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from stats_store import server_stats
import os

app = FastAPI()

API_KEY = os.getenv("API_SECRET_KEY", "")

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
def get_stats(x_api_key: str = Header(None)):
    # If API_SECRET_KEY is configured, enforce it
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return server_stats

@app.get("/health")
def health_check():
    return {"status": "ok"}
