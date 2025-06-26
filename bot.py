# === Final Telegram Movie Bot + Flask Website Code ===

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

# === CONFIGURATION ===
MONGO_URI = "mongodb+srv://manogog673:manogog673@cluster0.ot1qt.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
TMDB_API_KEY = "7dc544d9253bccc3cfecc1c677f69819"
CHANNEL_USERNAME = "autoposht"
BOT_USERNAME = "CtgAutoPostBot"  # Without @
API_ID = 22697010
API_HASH = "fd88d7339b0371eb2a9501d523f3e2a7"
BOT_TOKEN = "7347631253:AAFX3dmD0N8q6u0l2zghoBFu-7TXvMC571M"
ADMIN_PASSWORD = "Nahid270"

# === MongoDB Setup ===
mongo = pymongo.MongoClient(MONGO_URI)
db = mongo["movie_db"]
collection = db["movies"]

# === Pyrogram Bot ===
bot = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# === HTML Templates ===
INDEX_HTML = """..."""
MOVIE_HTML = """..."""
ADMIN_HTML = """..."""
LOGIN_HTML = """..."""

# === Utils ===
def extract_info(text):
    pattern = r"(.+?)(?:\s*\((\d{4})\))?\s*(?:-|\s+)?(\d{3,4}p|HD|SD|FHD)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        title = match.group(1).strip()
        year = match.group(2) if match.group(2) else "Unknown"
        quality = match.group(3).strip()
        return title, year, quality
    return None, None, None

def get_tmdb_info(title, year):
    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}"
    if year and year != "Unknown":
        url += f"&year={year}"
    try:
        res = requests.get(url).json()
        if res.get("results"):
            m = res["results"][0]
            poster_path = m.get('poster_path')
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
            overview = m.get("overview", "No overview available.")
            found_year = str(m.get('release_date', '')[:4])
            if found_year and (not year or year == "Unknown" or year != found_year):
                year = found_year
            return {
                "title": m.get('title', title),
                "year": year,
                "poster_url": poster_url,
                "overview": overview
            }
    except:
        pass
    return {"title": title, "year": year, "poster_url": "", "overview": "No overview available."}

# === Channel Post Handler ===
@bot.on_message(filters.channel & (filters.video | filters.document))
async def save_movie(client, message):
    if not message.caption:
        return
    title, year, quality = extract_info(message.caption)
    if not title or not quality:
        return
    file_id = message.video.file_id if message.video else message.document.file_id
    tmdb = get_tmdb_info(title, year)
    actual_title = tmdb['title']
    actual_year = tmdb['year']
    slug = f"{slugify(actual_title)}-{actual_year}"
    now = datetime.utcnow()
    quality_data = {"quality": quality, "file_id": file_id}
    existing = collection.find_one({"title": actual_title, "year": actual_year})
    if existing:
        qualities = existing.get("qualities", [])
        for q in qualities:
            if q["quality"] == quality:
                q["file_id"] = file_id
                break
        else:
            qualities.append(quality_data)
        collection.update_one({"_id": existing["_id"]}, {"$set": {
            "overview": tmdb["overview"],
            "poster_url": tmdb["poster_url"],
            "qualities": qualities,
            "slug": slug,
            "last_updated": now
        }})
    else:
        collection.insert_one({
            "title": actual_title,
            "year": actual_year,
            "language": "Unknown",
            "overview": tmdb["overview"],
            "poster_url": tmdb["poster_url"],
            "qualities": [quality_data],
            "slug": slug,
            "created_at": now,
            "last_updated": now
        })

# === /start command ===
@bot.on_message(filters.private & filters.command("start"))
async def start_cmd(client, message):
    if len(message.command) > 1:
        param = message.command[1]
        if param.startswith("stream_") or param.startswith("download_"):
            file_id = param.split("_", 1)[1]
            await client.send_document(
                chat_id=message.chat.id,
                file_id=file_id,
                caption="✅ Here is your requested file!"
            )
    else:
        await message.reply_text("🎬 Welcome to Movie Bot! Use website to browse movies.")

# === Flask App Setup ===
app = Flask(__name__)
app.secret_key = os.urandom(24)

@app.route("/")
def home():
    movies = list(collection.find().sort([("last_updated", -1), ("created_at", -1)]))
    return render_template_string(INDEX_HTML, movies=movies)

@app.route("/movie/<slug>")
def movie_detail(slug):
    movie = collection.find_one({"slug": slug})
    if not movie:
        return abort(404)
    return render_template_string(MOVIE_HTML, movie=movie)

@app.route("/watch/<file_id>")
def watch(file_id):
    return redirect(f"https://t.me/{BOT_USERNAME}?start=stream_{file_id}")

@app.route("/download/<file_id>")
def download(file_id):
    return redirect(f"https://t.me/{BOT_USERNAME}?start=download_{file_id}")

@app.route("/admin", methods=["GET"])
def admin():
    if session.get('logged_in'):
        movies = list(collection.find().sort([("last_updated", -1)]))
        return render_template_string(ADMIN_HTML, movies=movies)
    return render_template_string(LOGIN_HTML)

@app.route("/admin/login", methods=["POST"])
def admin_login():
    if request.form.get("password") == ADMIN_PASSWORD:
        session['logged_in'] = True
        return redirect("/admin")
    return render_template_string(LOGIN_HTML, error="Invalid Password")

@app.route("/admin/logout")
def logout():
    session.pop('logged_in', None)
    return redirect("/admin")

@app.route("/admin/delete/<mid>")
def delete(mid):
    if not session.get('logged_in'):
        return abort(403)
    collection.delete_one({"_id": ObjectId(mid)})
    return redirect("/admin")

# === Run ===
def run_web():
    app.run(host="0.0.0.0", port=5000, debug=False)

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    bot.run()
