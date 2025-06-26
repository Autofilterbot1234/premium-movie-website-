import threading
from pyrogram import Client, filters
import pymongo
import re
import requests
from flask import Flask, render_template_string, abort
from slugify import slugify
import asyncio  # asyncio ইম্পোর্ট করুন

# ===== CONFIGURATION =====
MONGO_URI = "mongodb+srv://manogog673:manogog673@cluster0.ot1qt.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
TMDB_API_KEY = "7dc544d9253bccc3cfecc1c677f69819"
CHANNEL_USERNAME = "autoposht"  # চ্যানেল ইউজারনেম, @ ছাড়া
API_ID = 22697010  # Telegram API ID
API_HASH = "fd88d7339b0371eb2a9501d523f3e2a7"
BOT_TOKEN = "7347631253:AAFX3dmD0N8q6u0l2zghoBFu-7TXvMC571M"

# ===== MongoDB Setup =====
mongo = pymongo.MongoClient(MONGO_URI)
db = mongo["movie_db"]
collection = db["movies"]

# ===== Pyrogram Client Setup =====
bot = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def extract_info(text):
    pattern = r"(.*?)(?:\s*?(\d{4})?)?\s*\|\s*(\d{3,4}p)"
    match = re.search(pattern, text)
    if match:
        title = match.group(1).strip()
        year = match.group(2) or "0000"
        quality = match.group(3)
        return title, year, quality
    return None, None, None

def get_tmdb_info(title, year):
    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}&year={year}"
    res = requests.get(url).json()
    if res.get("results"):
        movie = res["results"][0]
        return {
            "poster_url": f"https://image.tmdb.org/t/p/w500{movie.get('poster_path')}" if movie.get("poster_path") else "",
            "overview": movie.get("overview", "")
        }
    return {"poster_url": "", "overview": ""}

@bot.on_message(filters.channel & filters.video)
async def save_movie(client, message):
    if not message.caption:
        return

    title, year, quality = extract_info(message.caption)
    if not title or not quality:
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

# ===== Flask Web Server Setup =====

app = Flask(__name__)

INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>MovieZone - All Movies</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 900px; margin: auto; padding: 20px; background-color: #fafafa; color: #333; }
    h1 { text-align: center; margin-bottom: 20px; }
    .movies-grid { display: grid; grid-template-columns: repeat(auto-fill,minmax(180px,1fr)); gap: 15px; }
    .movie-card { text-decoration: none; color: #222; border: 1px solid #ddd; padding: 5px; border-radius: 6px; transition: box-shadow 0.2s ease; background: white; }
    .movie-card:hover { box-shadow: 0 0 10px #aaa; }
    .movie-card img { width: 100%; height: auto; border-radius: 4px; }
    .movie-info { text-align: center; margin-top: 8px; }
  </style>
</head>
<body>
  <h1>MovieZone - All Movies</h1>
  <div class="movies-grid">
    {% for movie in movies %}
      <a href="/movie/{{ movie.slug }}" class="movie-card">
        <img src="{{ movie.poster_url or 'https://via.placeholder.com/300x450?text=No+Image' }}" alt="{{ movie.title }}" />
        <div class="movie-info">
          <h3>{{ movie.title }} ({{ movie.year }})</h3>
        </div>
      </a>
    {% endfor %}
  </div>
</body>
</html>
"""

MOVIE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>{{ movie.title }} ({{ movie.year }})</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 900px; margin: auto; padding: 20px; background-color: #fafafa; color: #333; }
    a { color: #007BFF; text-decoration: none; }
    a:hover { text-decoration: underline; }
    table { width: 100%; border-collapse: collapse; margin-top: 15px; }
    th, td { padding: 10px; border: 1px solid #ddd; text-align: center; }
    img { max-width: 300px; border-radius: 6px; display: block; margin-bottom: 10px; }
  </style>
</head>
<body>
  <a href="/">&#8592; Back to Home</a>
  <h1>{{ movie.title }} ({{ movie.year }})</h1>
  <img src="{{ movie.poster_url or 'https://via.placeholder.com/300x450?text=No+Image' }}" alt="{{ movie.title }}" />
  <p>{{ movie.overview or "No description available." }}</p>

  <h2>Qualities</h2>
  <table>
    <tr>
      <th>Quality</th>
      <th>Watch</th>
      <th>Download</th>
    </tr>
    {% for q in movie.qualities %}
      <tr>
        <td>{{ q.quality }}</td>
        <td><a href="{{ q.watch_url }}" target="_blank">▶️ Watch</a></td>
        <td><a href="{{ q.download_url }}" target="_blank">⬇️ Download</a></td>
      </tr>
    {% endfor %}
  </table>
</body>
</html>
"""

def get_slug(title, year):
    return f"{slugify(title)}-{year}"

@app.route("/")
def home():
    movies = list(collection.find())
    for m in movies:
        m["slug"] = get_slug(m["title"], m["year"])
    return render_template_string(INDEX_HTML, movies=movies)

@app.route("/movie/<slug>")
def movie_detail(slug):
    try:
        title_part = slug.rsplit("-", 1)[0]
        year_part = slug.rsplit("-", 1)[1]
    except:
        abort(404)

    movie = collection.find_one({"year": year_part, "title": {"$regex": title_part, "$options": "i"}})
    if not movie:
        abort(404)
    movie["slug"] = slug
    return render_template_string(MOVIE_HTML, movie=movie)

# ===== Run Bot and Flask app concurrently =====

def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    bot.run()

def run_flask():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    t1 = threading.Thread(target=run_bot)
    t2 = threading.Thread(target=run_flask)
    t1.start()
    t2.start()
