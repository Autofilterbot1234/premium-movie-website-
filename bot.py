# bot.py

import os
from dotenv import load_dotenv
from pyrogram import Client, filters
from pymongo import MongoClient
from flask import Flask, render_template_string
import threading
import requests

# === Load environment variables ===
load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL = os.getenv("CHANNEL")
MONGO_URI = os.getenv("MONGO_URI")
OMDB_API_KEY = os.getenv("OMDB_API_KEY")

# === Database setup ===
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["movie_db"]
collection = db["movies"]

# === Flask Web App ===
app = Flask(__name__)

@app.route("/")
def index():
    movies = list(collection.find().sort("_id", -1))
    html = """
    <html><head>
    <title>🎬 Auto Movie Site</title>
    <style>
        body { font-family: sans-serif; background: #111; color: #eee; padding: 20px; }
        .movie { background: #222; border-radius: 10px; padding: 10px; margin: 15px 0; }
        img { width: 200px; border-radius: 5px; }
        a { color: #00f7ff; text-decoration: none; }
    </style></head><body>
    <h1>📺 Movie List</h1>
    {% for m in movies %}
    <div class="movie">
        <img src="{{m.poster}}"><br>
        <h2>{{m.title}} ({{m.year}})</h2>
        <p>Language: {{m.language}} | ⭐ IMDb: {{m.rating}}</p>
        <p>{{m.plot}}</p>
        <a href="{{m.link}}">📥 Download / 🎬 Watch</a>
    </div>
    {% endfor %}
    </body></html>
    """
    return render_template_string(html, movies=movies)

# === Telegram Bot ===
bot = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@bot.on_message(filters.chat(CHANNEL) & filters.media)
async def movie_handler(client, message):
    caption = message.caption or ""
    title_line = caption.split("\n")[0] if caption else "Unknown"
    print(f"🎬 Processing: {title_line}")

    try:
        url = f"http://www.omdbapi.com/?t={title_line}&apikey={OMDB_API_KEY}"
        data = requests.get(url).json()

        if data.get("Response") != "True":
            print("❌ Movie not found on OMDb")
            return

        movie = {
            "title": data.get("Title"),
            "year": data.get("Year"),
            "language": data.get("Language"),
            "rating": data.get("imdbRating"),
            "poster": data.get("Poster"),
            "plot": data.get("Plot"),
            "link": f"https://t.me/{CHANNEL.strip('@')}/{message.id}"
        }

        if not collection.find_one({"title": movie["title"], "year": movie["year"]}):
            collection.insert_one(movie)
            print(f"✅ Saved: {movie['title']}")
        else:
            print("⚠️ Already exists.")

    except Exception as e:
        print(f"🚨 Error: {e}")

# === Run Bot & Server ===
if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()
    bot.run()
