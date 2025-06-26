import threading
import asyncio
from pyrogram import Client, filters
import pymongo
import re
import requests
from flask import Flask, render_template, request, redirect, abort
from slugify import slugify
from bson.objectid import ObjectId

# ===== CONFIGURATION =====
MONGO_URI = "mongodb+srv://manogog673:manogog673@cluster0.ot1qt.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
TMDB_API_KEY = "7dc544d9253bccc3cfecc1c677f69819"
CHANNEL_USERNAME = "autoposht"
BOT_USERNAME = "CtgAutoPostBot"
API_ID = 22697010
API_HASH = "fd88d7339b0371eb2a9501d523f3e2a7"
BOT_TOKEN = "7347631253:AAFX3dmD0N8q6u0l2zghoBFu-7TXvMC571M"
ADMIN_TOKEN = "admin123"  # Change this strong for production!

# ===== MongoDB Setup =====
mongo = pymongo.MongoClient(MONGO_URI)
db = mongo["movie_db"]
collection = db["movies"]

# ===== Pyrogram Bot Setup =====
bot = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def extract_info(text):
    # মুভি টাইটেল, ইয়ার, কোয়ালিটি বের করার জন্য Regex
    pattern = r"(.*?)(?:\s+(\d{4}))?\s*(?:\||-|–)?\s*(\d{3,4}p)"
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
            poster_url = f"https://image.tmdb.org/t/p/w500{movie.get('poster_path')}" if movie.get("poster_path") else ""
            overview = movie.get("overview", "")
            return {"poster_url": poster_url, "overview": overview}
    except:
        pass
    return {"poster_url": "", "overview": ""}

@bot.on_message(filters.channel & (filters.video | filters.document))
async def save_movie(client, message):
    if not message.caption:
        return

    title, year, quality = extract_info(message.caption)
    if not title or not quality:
        print("[✘] Caption did not match title or quality pattern")
        return

    file_id = message.video.file_id if message.video else message.document.file_id
    tmdb_info = get_tmdb_info(title, year)

    existing = collection.find_one({"title": title, "year": year})
    quality_entry = {"quality": quality, "file_id": file_id}

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

# ===== Flask Web Server =====
app = Flask(__name__)

@app.route("/")
def home():
    movies = list(collection.find())
    for m in movies:
        m["slug"] = f"{slugify(m['title'])}-{m['year']}"
    return render_template("index.html", movies=movies)

@app.route("/movie/<slug>")
def movie_detail(slug):
    try:
        title_part = slug.rsplit("-", 1)[0]
        year_part = slug.rsplit("-", 1)[1]
    except:
        abort(404)

    movie = collection.find_one({"year": year_part, "title": {"$regex": f"^{re.escape(title_part)}$", "$options": "i"}})
    if not movie:
        # Try partial match if exact not found
        movie = collection.find_one({"year": year_part, "title": {"$regex": title_part, "$options": "i"}})
    if not movie:
        abort(404)

    return render_template("movie.html", movie=movie)

@app.route("/watch/<file_id>")
def watch_video(file_id):
    # Telegram bot start param for streaming (customize if needed)
    return redirect(f"https://t.me/{BOT_USERNAME}?start=stream_{file_id}")

@app.route("/download/<file_id>")
def download_video(file_id):
    # Telegram bot start param for download (customize if needed)
    return redirect(f"https://t.me/{BOT_USERNAME}?start=download_{file_id}")

# Admin panel
@app.route("/admin")
def admin_panel():
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        abort(403)
    movies = list(collection.find())
    return render_template("admin.html", movies=movies, token=ADMIN_TOKEN)

@app.route("/admin/delete/<mid>")
def delete_movie(mid):
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        abort(403)
    try:
        collection.delete_one({"_id": ObjectId(mid)})
    except:
        abort(400)
    return redirect(f"/admin?token={ADMIN_TOKEN}")

# ===== Run bot and Flask concurrently =====
def run_flask():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.run()
