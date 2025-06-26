# ✅ Final Version: Telegram Movie Bot with auto caption parser, fallback handling, web display, TMDB integration

import threading
import asyncio
from pyrogram import Client, filters
import pymongo
import re
import requests
from flask import Flask, request, redirect, abort, render_template_string, session, url_for
from slugify import slugify
import os
from bson.objectid import ObjectId
from datetime import datetime

# ===== CONFIGURATION =====
MONGO_URI = "mongodb+srv://manogog673:manogog673@cluster0.ot1qt.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
TMDB_API_KEY = "7dc544d9253bccc3cfecc1c677f69819"
CHANNEL_USERNAME = "autoposht"
BOT_USERNAME = "CtgAutoPostBot"  # without @
API_ID = 22697010
API_HASH = "fd88d7339b0371eb2a9501d523f3e2a7"
BOT_TOKEN = "7347631253:AAFX3dmD0N8q6u0l2zghoBFu-7TXvMC571M"
ADMIN_PASSWORD = "Nahid270"

# ===== MongoDB Setup =====
mongo = pymongo.MongoClient(MONGO_URI)
db = mongo["movie_db"]
collection = db["movies"]

# ===== Pyrogram Bot Setup =====
bot = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== Templates =====
INDEX_HTML = """<html><body><h1>All Movies</h1>{% for movie in movies %}<div><a href='/movie/{{movie.slug}}'>{{movie.title}} ({{movie.year}})</a></div>{% endfor %}</body></html>"""
MOVIE_HTML = """<html><body><h1>{{ movie.title }} ({{ movie.year }})</h1><img src='{{ movie.poster_url }}' /><p>{{ movie.overview }}</p>{% for q in movie.qualities %}<div>{{q.quality}}: <a href='/watch/{{q.file_id}}'>Watch</a> | <a href='/download/{{q.file_id}}'>Download</a></div>{% endfor %}<br><a href='/'>⬅ Back</a></body></html>"""
LOGIN_HTML = """<form method='post'><input name='password' type='password'/><button>Login</button>{% if error %}<p>{{error}}</p>{% endif %}</form>"""
ADMIN_HTML = """<h1>Admin</h1><ul>{% for movie in movies %}<li>{{movie.title}} ({{movie.year}}) <a href='/admin/delete/{{movie._id}}'>Delete</a></li>{% endfor %}</ul><a href='/admin/logout'>Logout</a>"""

# ===== Utility Functions =====
def extract_info(text):
    pattern = r"(.+?)(?:\s*\((\d{4})\))?.*?(\d{3,4}p|HD|SD|FHD)?"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        title = match.group(1).strip()
        year = match.group(2) or "Unknown"
        quality = match.group(3) or "Unknown"
        return title, year, quality
    return text.strip(), "Unknown", "Unknown"

def get_tmdb_info(title, year):
    try:
        url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}"
        if year != "Unknown":
            url += f"&year={year}"
        res = requests.get(url).json()
        if res.get("results"):
            m = res["results"][0]
            poster = f"https://image.tmdb.org/t/p/w500{m['poster_path']}" if m.get('poster_path') else ""
            return {
                "title": m.get("title", title),
                "year": m.get("release_date", "")[:4] or year,
                "poster_url": poster,
                "overview": m.get("overview", "No overview")
            }
    except: pass
    return {"title": title, "year": year, "poster_url": "", "overview": "No overview"}

# ===== Bot Handler =====
@bot.on_message(filters.channel & (filters.video | filters.document))
async def save_movie(client, message):
    if not message.caption:
        return
    title, year, quality = extract_info(message.caption)
    file_id = message.video.file_id if message.video else message.document.file_id
    tmdb = get_tmdb_info(title, year)
    slug = f"{slugify(tmdb['title'])}-{tmdb['year']}"
    now = datetime.now()
    existing = collection.find_one({"title": tmdb['title'], "year": tmdb['year']})
    quality_entry = {"quality": quality, "file_id": file_id}
    if existing:
        for q in existing["qualities"]:
            if q["quality"] == quality:
                q.update(quality_entry)
                break
        else:
            existing["qualities"].append(quality_entry)
        collection.update_one({"_id": existing["_id"]}, {"$set": {
            "qualities": existing["qualities"], "last_updated": now
        }})
    else:
        collection.insert_one({
            "title": tmdb['title'], "year": tmdb['year'], "overview": tmdb['overview'],
            "poster_url": tmdb['poster_url'], "slug": slug,
            "qualities": [quality_entry], "created_at": now, "last_updated": now
        })

# ===== Flask Setup =====
app = Flask(__name__)
app.secret_key = os.urandom(24)

@app.route("/")
def home():
    movies = list(collection.find().sort("last_updated", -1))
    return render_template_string(INDEX_HTML, movies=movies)

@app.route("/movie/<slug>")
def movie_detail(slug):
    movie = collection.find_one({"slug": slug})
    if not movie: return abort(404)
    return render_template_string(MOVIE_HTML, movie=movie)

@app.route("/watch/<file_id>")
def watch(file_id):
    return redirect(f"https://t.me/{BOT_USERNAME}?start=stream_{file_id}")

@app.route("/download/<file_id>")
def download(file_id):
    return redirect(f"https://t.me/{BOT_USERNAME}?start=download_{file_id}")

@app.route("/admin", methods=["GET"])
def admin():
    if session.get("logged_in"):
        movies = list(collection.find().sort("last_updated", -1))
        return render_template_string(ADMIN_HTML, movies=movies)
    return render_template_string(LOGIN_HTML)

@app.route("/admin/login", methods=["POST"])
def login():
    if request.form.get("password") == ADMIN_PASSWORD:
        session['logged_in'] = True
        return redirect("/admin")
    return render_template_string(LOGIN_HTML, error="Wrong Password")

@app.route("/admin/logout")
def logout():
    session.pop("logged_in", None)
    return redirect("/admin")

@app.route("/admin/delete/<mid>")
def delete(mid):
    if not session.get("logged_in"): return abort(403)
    collection.delete_one({"_id": ObjectId(mid)})
    return redirect("/admin")

# ===== Run Both =====
def run_flask():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.run()
