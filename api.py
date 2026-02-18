from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from stats_store import server_stats

app = FastAPI()

# Allow your website to access API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # later replace with your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/stats")
def get_stats():
    return server_stats
