from flask import Flask, render_template
import os

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/status')
def status():
    return {"status": "Bot is online!", "message": "Discord bot is running smoothly."}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Use assigned port or default to 5000
    app.run(host='0.0.0.0', port=port)
