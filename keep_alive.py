from flask import Flask
from threading import Thread
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is alive!"

def run():
    # Render assigns the public port via $PORT (typically 10000).
    # Flask binds here so Render's health checks pass.
    port = int(os.environ.get("PORT", 5000))
    print(f"Running Flask keep_alive on port {port}")
    # use_reloader=False prevents Flask from spawning a second process
    # which can cause duplicate thread issues on Render.
    app.run(host='0.0.0.0', port=port, use_reloader=False)

def keep_alive():
    # FIX: daemon=True so this thread dies when the main process exits,
    #      preventing the bot from hanging on shutdown.
    t = Thread(target=run, daemon=True)
    t.start()

if __name__ == "__main__":
    run()
