# bot.py

from pyrogram import Client, filters
from pymongo import MongoClient
from flask import Flask, render_template_string
import requests
import threading
import os

# ======= CONFIGURATION =======
API_ID = 123456               # তোমার Pyrogram API_ID
API_HASH = "your_api_hash"    # তোমার Pyrogram API_HASH
BOT_TOKEN = "your_bot_token"  # BotFather থেকে নেওয়া Token
CHANNEL = "@yourchannel"      # তোমার মুভি চ্যানেল ইউজারনেম
MONGO_URI = "your_mongo_uri"  # MongoDB URI
OMDB_API_KEY = "your_omdb_api_key"  # omdbapi.com থেকে নেওয়া API Key

# ======= DATABASE SETUP =======
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["movie_db"]
collection = db["movies"]

# ======= FLASK WEB SERVER =======
app = Flask(__name__)

@app.route("/")
def index():
    movies = list(collection.find().sort("_id", -1))
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>🎬 Auto Movie Site</title>
        <style>
            body { font-family: Arial; background: #111; color: #eee; }
            .movie { border: 1px solid #444; margin: 10px; padding: 10px; border-radius: 10px; background: #222; }
            img { width: 200px; border-radius: 5px; }
            a { color: #00f7ff; text-decoration: none; }
        </style>
    </head>
    <body>
        <h1>🎬 Auto Movie Website</h1>
        {% for m in movies %}
        <div class="movie">
            <img src="{{m.poster}}" alt="Poster"><br>
            <h2>{{m.title}} ({{m.year}})</h2>
            <p>Language: {{m.language}} | ⭐ IMDb: {{m.rating}}</p>
            <p>{{m.plot}}</p>
            <p>
                <a href="{{m.link}}">📥 Download / 🎬 Watch</a>
            </p>
        </div>
        {% endfor %}
    </body>
    </html>
    """
    return render_template_string(html, movies=movies)

# ======= TELEGRAM BOT SETUP =======
bot = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@bot.on_message(filters.channel & filters.chat(CHANNEL))
async def save_movie(client, message):
    if not (message.video or message.document):
        return

    caption = message.caption or ""
    title_line = caption.split("\n")[0] if caption else "Unknown Movie"
    print(f"🎬 Found: {title_line}")

    # OMDb API Call
    try:
        url = f"http://www.omdbapi.com/?t={title_line}&apikey={OMDB_API_KEY}"
        response = requests.get(url).json()
        if response.get("Response") != "True":
            print("❌ Movie not found on OMDb")
            return

        movie_data = {
            "title": response.get("Title"),
            "year": response.get("Year"),
            "language": response.get("Language"),
            "rating": response.get("imdbRating"),
            "poster": response.get("Poster"),
            "plot": response.get("Plot"),
            "link": f"https://t.me/{CHANNEL.strip('@')}/{message.id}"
        }

        if collection.find_one({"title": movie_data["title"], "year": movie_data["year"]}):
            print("⚠️ Already exists")
            return

        collection.insert_one(movie_data)
        print(f"✅ Saved: {movie_data['title']}")

    except Exception as e:
        print(f"⚠️ Error: {e}")

# ======= RUN BOTH BOT + WEBSITE =======
if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()
    bot.run()
