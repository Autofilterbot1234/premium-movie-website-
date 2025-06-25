# bot.py

from pyrogram import Client, filters
from pymongo import MongoClient
from flask import Flask, jsonify, render_template_string
import requests, os

# --- CONFIGURATION ---
BOT_TOKEN = "YOUR_BOT_TOKEN"
API_ID = 123456
API_HASH = "YOUR_API_HASH"
CHANNEL = "YourChannelUsername"
OMDB_API_KEY = "YOUR_OMDB_API_KEY"
MONGO_URI = "YOUR_MONGO_URI"

# --- MONGODB SETUP ---
client = MongoClient(MONGO_URI)
db = client["movie_db"]
collection = db["movies"]

# --- FLASK APP ---
app = Flask(__name__)

@app.route("/")
def index():
    movies = list(collection.find().sort("_id", -1))
    html = """
    <html>
    <head><title>Movie List</title></head>
    <body>
        <h1>🎬 Auto Movie Website</h1>
        {% for m in movies %}
        <div style="border:1px solid #ccc;padding:10px;margin:10px;">
            <img src="{{m.poster}}" width="150"/>
            <h2>{{m.title}} ({{m.year}}) [{{m.language}}]</h2>
            <p>⭐ IMDb: {{m.rating}}</p>
            <a href="{{m.link}}">📥 Download</a>
        </div>
        {% endfor %}
    </body>
    </html>
    """
    return render_template_string(html, movies=movies)

# --- TELEGRAM BOT ---
bot = Client("movie_bot", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

@bot.on_message(filters.channel & filters.chat(CHANNEL))
async def movie_handler(client, message):
    if not message.video and not message.document:
        return

    title = message.caption.split("\n")[0] if message.caption else "Unknown"
    print(f"Found movie: {title}")

    # --- IMDb Info Fetch ---
    r = requests.get(f"http://www.omdbapi.com/?t={title}&apikey={OMDB_API_KEY}")
    data = r.json()
    if data.get("Response") != "True":
        return

    movie = {
        "title": data.get("Title"),
        "year": data.get("Year"),
        "language": data.get("Language", "Unknown"),
        "rating": data.get("imdbRating"),
        "poster": data.get("Poster"),
        "link": f"https://t.me/{CHANNEL.strip('@')}/{message.id}"
    }

    collection.insert_one(movie)
    print(f"✅ Saved: {movie['title']}")

# --- RUN ---
if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()
    bot.run()
