import threading
import asyncio
from pyrogram import Client, filters
import pymongo
import re
import requests
from flask import Flask, render_template_string, abort
from slugify import slugify

# ===== CONFIGURATION =====
MONGO_URI = "mongodb+srv://manogog673:manogog673@cluster0.ot1qt.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
TMDB_API_KEY = "7dc544d9253bccc3cfecc1c677f69819"
CHANNEL_USERNAME = "autoposht"
API_ID = 22697010
API_HASH = "fd88d7339b0371eb2a9501d523f3e2a7"
BOT_TOKEN = "7347631253:AAFX3dmD0N8q6u0l2zghoBFu-7TXvMC571M"

# ===== MongoDB Setup =====
mongo = pymongo.MongoClient(MONGO_URI)
db = mongo["movie_db"]
collection = db["movies"]

# ===== Pyrogram Bot Setup =====
bot = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def extract_info(text):
    pattern = r"(.*?)(?:\s*(\d{4}))?\s*(?:\||-|–)?\s*(\d{3,4}p)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        title = match.group(1).strip()
        year = match.group(2) or "0000"
        quality = match.group(3)
        return title, year, quality
    return None, None, None

def get_tmdb_info(title, year):
    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}&year={year}"
    try:
        res = requests.get(url).json()
        if res.get("results"):
            movie = res["results"][0]
            return {
                "poster_url": f"https://image.tmdb.org/t/p/w500{movie.get('poster_path')}" if movie.get("poster_path") else "",
                "overview": movie.get("overview", "")
            }
    except:
        pass
    return {"poster_url": "", "overview": ""}

@bot.on_message(filters.channel & (filters.video | filters.document))
async def save_movie(client, message):
    if not message.caption:
        return

    title, year, quality = extract_info(message.caption)
    if not title or not quality:
        print("[✘] Title or quality not matched in caption")
        return

    link = f"https://t.me/{CHANNEL_USERNAME}/{message.id}"
    tmdb_info = get_tmdb_info(title, year)

    existing = collection.find_one({"title": title, "year": year})
    quality_entry = {"quality": quality, "download_url": link, "watch_url": link}

    if existing:
        updated = False
        for q in existing["qualities"]:
            if q["quality"] == quality:
                q.update(quality_entry)
                updated = True
                break
        if not updated:
            existing["qualities"].append(quality_entry)
        collection.update_one({"_id": existing["_id"]}, {"$set": existing})
    else:
        collection.insert_one({
            "title": title,
            "year": year,
            "language": "Unknown",
            "overview": tmdb_info["overview"],
            "poster_url": tmdb_info["poster_url"],
            "qualities": [quality_entry]
        })
    print(f"[✔] Saved: {title} ({year}) - {quality}")

# ===== Flask Web Setup =====
app = Flask(__name__)

INDEX_HTML = """
<!DOCTYPE html>
<html><head><title>Movie List</title></head><body><h1>Movies</h1>
<ul>
{% for movie in movies %}
  <li><a href="/movie/{{ movie.slug }}">{{ movie.title }} ({{ movie.year }})</a></li>
{% endfor %}
</ul></body></html>
"""

MOVIE_HTML = """
<!DOCTYPE html>
<html><head><title>{{ movie.title }}</title></head><body>
<h1>{{ movie.title }} ({{ movie.year }})</h1>
<img src="{{ movie.poster_url or 'https://via.placeholder.com/300x450?text=No+Image' }}"><br>
<p>{{ movie.overview or 'No description available.' }}</p>
<ul>
{% for q in movie.qualities %}
  <li>{{ q.quality }}:
    <a href="{{ q.watch_url }}">▶️ Watch</a> |
    <a href="{{ q.download_url }}">⬇️ Download</a>
  </li>
{% endfor %}
</ul>
<a href="/">Back</a>
</body></html>
"""

def get_slug(title, year):
    return f"{slugify(title)}-{year}"

@app.route("/")
def home():
    movies = list(collection.find())
    for m in movies:
        m["slug"] = get_slug(m["title"], m["year"])
    return render_template_string(INDEX_HTML, movies=movies)

@app.route("/movie/<path:slug>")
def movie_detail(slug):
    try:
        title_part = slug.rsplit("-", 1)[0]
        year_part = slug.rsplit("-", 1)[1]
    except:
        abort(404)

    movie = collection.find_one({"year": year_part, "title": {"$regex": f"^{re.escape(title_part)}$", "$options": "i"}})
    if not movie:
        abort(404)
    movie["slug"] = slug
    return render_template_string(MOVIE_HTML, movie=movie)

# ===== Run Flask + Bot together =====
def run_flask():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    bot.run()
