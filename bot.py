import threading
import asyncio
from pyrogram import Client, filters
import pymongo
import re
import requests
from flask import Flask, request, redirect, abort, render_template_string
from slugify import slugify

# ===== CONFIGURATION =====
MONGO_URI = "mongodb+srv://manogog673:manogog673@cluster0.ot1qt.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
TMDB_API_KEY = "7dc544d9253bccc3cfecc1c677f69819"
CHANNEL_USERNAME = "autoposht"
BOT_USERNAME = "CtgAutoPostBot"
API_ID = 22697010
API_HASH = "fd88d7339b0371eb2a9501d523f3e2a7"
BOT_TOKEN = "7347631253:AAFX3dmD0N8q6u0l2zghoBFu-7TXvMC571M"
ADMIN_TOKEN = "admin123"

# ===== MongoDB Setup =====
mongo = pymongo.MongoClient(MONGO_URI)
db = mongo["movie_db"]
collection = db["movies"]

# ===== Pyrogram Bot Setup =====
bot = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== Template HTMLs =====
INDEX_HTML = """
<!DOCTYPE html>
<html><head><title>MovieZone - All Movies</title>
<style>
body { font-family: sans-serif; background: #f0f0f0; max-width: 900px; margin: auto; padding: 20px; }
.movies-grid { display: grid; grid-template-columns: repeat(auto-fill,minmax(180px,1fr)); gap: 15px; }
.movie-card { text-decoration: none; color: #000; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); transition: transform 0.2s; }
.movie-card:hover { transform: scale(1.03); }
.movie-card img { width: 100%; height: auto; }
.movie-title { padding: 10px; text-align: center; font-weight: bold; }
</style></head>
<body><h1>MovieZone - All Movies</h1>
<div class="movies-grid">
{% for movie in movies %}
<a class="movie-card" href="/movie/{{ movie.slug }}">
<img src="{{ movie.poster_url or 'https://via.placeholder.com/300x450?text=No+Image' }}">
<div class="movie-title">{{ movie.title }} ({{ movie.year }})</div>
</a>
{% endfor %}
</div></body></html>
"""

MOVIE_HTML = """
<!DOCTYPE html>
<html><head><title>{{ movie.title }}</title>
<style>
body { font-family: sans-serif; max-width: 800px; margin: auto; padding: 20px; background: #fff; }
img { max-width: 300px; float: left; margin-right: 20px; border-radius: 8px; }
h1 { margin-top: 0; }
.btn { display: inline-block; margin: 5px 10px; padding: 10px 20px; background: #007BFF; color: white; border-radius: 5px; text-decoration: none; }
.btn:hover { background: #0056b3; }
.clear { clear: both; }
</style></head>
<body><h1>{{ movie.title }} ({{ movie.year }})</h1>
<img src="{{ movie.poster_url or 'https://via.placeholder.com/300x450?text=No+Image' }}">
<p>{{ movie.overview }}</p>
<div class="clear"></div>
{% for q in movie.qualities %}
<p><b>{{ q.quality }}</b>:
<a class="btn" href="/watch/{{ q.file_id }}">▶️ Watch</a>
<a class="btn" href="/download/{{ q.file_id }}">⬇️ Download</a></p>
{% endfor %}
<p><a href="/">← Back</a></p></body></html>
"""

ADMIN_HTML = """
<html><head><title>Admin Panel</title></head><body>
<h1>Admin Panel</h1>
<ul>
{% for movie in movies %}
<li>{{ movie.title }} ({{ movie.year }}) <a href='/admin/delete/{{ movie._id }}?token={{ token }}'>❌ Delete</a></li>
{% endfor %}
</ul>
</body></html>
"""

def extract_info(text):
    pattern = r"(.*?)(?:\s*(\d{4}))?\s*(?:\||-|–)?\s*(\d{3,4}p)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).strip(), match.group(2) or "0000", match.group(3)
    return None, None, None

def get_tmdb_info(title, year):
    try:
        url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}&year={year}"
        res = requests.get(url).json()
        if res.get("results"):
            m = res["results"][0]
            return {
                "poster_url": f"https://image.tmdb.org/t/p/w500{m.get('poster_path')}" if m.get("poster_path") else "",
                "overview": m.get("overview", "")
            }
    except: pass
    return {"poster_url": "", "overview": ""}

@bot.on_message(filters.channel & (filters.video | filters.document))
async def save_movie(client, message):
    if not message.caption:
        return
    title, year, quality = extract_info(message.caption)
    if not title or not quality:
        return
    file_id = message.video.file_id if message.video else message.document.file_id
    tmdb_info = get_tmdb_info(title, year)
    existing = collection.find_one({"title": title, "year": year})
    quality_entry = {"quality": quality, "file_id": file_id}
    if existing:
        for q in existing["qualities"]:
            if q["quality"] == quality:
                q.update(quality_entry)
                break
        else:
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

# ===== Flask App Setup =====
app = Flask(__name__)

@app.route("/")
def home():
    movies = list(collection.find())
    for m in movies:
        m["slug"] = f"{slugify(m['title'])}-{m['year']}"
    return render_template_string(INDEX_HTML, movies=movies)

@app.route("/movie/<slug>")
def movie_detail(slug):
    try:
        title, year = slug.rsplit("-", 1)
    except:
        return abort(404)
    movie = collection.find_one({"year": year, "title": {"$regex": f"^{re.escape(title)}", "$options": "i"}})
    if not movie:
        return abort(404)
    return render_template_string(MOVIE_HTML, movie=movie)

@app.route("/watch/<file_id>")
def watch(file_id):
    return redirect(f"https://t.me/{BOT_USERNAME}?start=stream_{file_id}")

@app.route("/download/<file_id>")
def download(file_id):
    return redirect(f"https://t.me/{BOT_USERNAME}?start=download_{file_id}")

@app.route("/admin")
def admin():
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return abort(403)
    movies = list(collection.find())
    return render_template_string(ADMIN_HTML, movies=movies, token=token)

@app.route("/admin/delete/<mid>")
def delete(mid):
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return abort(403)
    collection.delete_one({"_id": pymongo.ObjectId(mid)})
    return redirect(f"/admin?token={token}")

# ===== RUN BOTH =====
def run():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    threading.Thread(target=run).start()
    bot.run()
