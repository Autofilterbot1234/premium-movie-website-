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
    clean_text = re.sub(r"[^\w\s\d]|_", " ", text)
    clean_text = re.sub(r"\s+", " ", clean_text).strip()
    match = re.search(r"(.+?)\s*(\d{4})\s*(\d{3,4}p)", clean_text, re.IGNORECASE)
    if match:
        title = match.group(1).strip()
        year = match.group(2)
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

    slug = slugify(title) + f"-{year}"

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
            "slug": slug,
            "qualities": [quality_entry]
        })
    print(f"[✔] Saved: {title} ({year}) - {quality}")

# ===== Flask Setup =====
app = Flask(__name__)

INDEX_HTML = """
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>MovieZone</title>
  <style>
    body { font-family: Arial, sans-serif; background: #111; color: #fff; margin: 0; padding: 20px; }
    h1 { text-align: center; margin-bottom: 30px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 20px; }
    .card { background: #222; border-radius: 10px; padding: 10px; text-align: center; text-decoration: none; color: white; transition: 0.3s; }
    .card:hover { background: #333; }
    .card img { width: 100%; border-radius: 6px; height: 220px; object-fit: cover; }
    .card-title { margin-top: 10px; font-size: 16px; }
  </style>
</head>
<body>
  <h1>MovieZone</h1>
  <div class=\"grid\">
    {% for movie in movies %}
    <a href=\"/movie/{{ movie.slug }}\" class=\"card\">
      <img src=\"{{ movie.poster_url or 'https://via.placeholder.com/300x450?text=No+Image' }}\" alt=\"Poster\">
      <div class=\"card-title\">{{ movie.title }}<br>({{ movie.year }})</div>
    </a>
    {% endfor %}
  </div>
</body>
</html>
"""

MOVIE_HTML = """
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>{{ movie.title }}</title>
  <style>
    body { font-family: Arial, sans-serif; background: #111; color: #fff; padding: 20px; }
    a { color: #1e90ff; }
    .container { max-width: 800px; margin: auto; }
    img { width: 100%; max-width: 300px; border-radius: 10px; }
    table { width: 100%; margin-top: 20px; border-collapse: collapse; }
    th, td { padding: 10px; border-bottom: 1px solid #444; text-align: center; }
    h1 { margin-top: 10px; }
  </style>
</head>
<body>
  <div class=\"container\">
    <a href=\"/\">← Back to Home</a>
    <h1>{{ movie.title }} ({{ movie.year }})</h1>
    <img src=\"{{ movie.poster_url or 'https://via.placeholder.com/300x450?text=No+Image' }}\" alt=\"Poster\">
    <p>{{ movie.overview }}</p>

    <h2>Available Qualities</h2>
    <table>
      <tr><th>Quality</th><th>Watch</th><th>Download</th></tr>
      {% for q in movie.qualities %}
      <tr>
        <td>{{ q.quality }}</td>
        <td><a href=\"{{ q.watch_url }}\" target=\"_blank\">▶️ Watch</a></td>
        <td><a href=\"{{ q.download_url }}\" target=\"_blank\">⬇️ Download</a></td>
      </tr>
      {% endfor %}
    </table>
  </div>
</body>
</html>
"""

@app.route("/")
def home():
    movies = list(collection.find())
    return render_template_string(INDEX_HTML, movies=movies)

@app.route("/movie/<path:slug>")
def movie_detail(slug):
    try:
        title_part = slug.rsplit("-", 1)[0].replace("-", " ").strip()
        year_part = slug.rsplit("-", 1)[1]
    except:
        abort(404)

    movie = collection.find_one({
        "year": year_part,
        "title": {"$regex": f"^{re.escape(title_part)}$", "$options": "i"}
    })

    if not movie:
        abort(404)
    movie["slug"] = slug
    return render_template_string(MOVIE_HTML, movie=movie)

# ===== Run Flask in background, Bot in main =====
def run_flask():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    bot.run()
