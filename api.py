from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from stats_store import server_stats

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with your domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
@app.head("/")
def root():
    # Render health-checks both Flask (port $PORT) and any open port it detects.
    # Without this route uvicorn returns 404 on HEAD /, which can cause Render
    # to flag the service as unhealthy.
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    # FIX: server_stats is now populated and kept up-to-date by the bot
    #      in on_ready, on_guild_join, and on_guild_remove events in main.py.
    #      Previously this always returned zeros because nothing ever wrote to it.
    return server_stats

@app.get("/health")
def health_check():
    return {"status": "ok"}
