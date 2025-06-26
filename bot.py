# ===================== FULL FINAL BOT + WEBSITE =====================

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

# ===================== CONFIG =====================

MONGO_URI = "mongodb+srv://manogog673:manogog673@cluster0.ot1qt.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
TMDB_API_KEY = "7dc544d9253bccc3cfecc1c677f69819"
CHANNEL_USERNAME = "autoposht"
BOT_USERNAME = "CtgAutoPostBot"
API_ID = 22697010
API_HASH = "fd88d7339b0371eb2a9501d523f3e2a7"
BOT_TOKEN = "7347631253:AAFX3dmD0N8q6u0l2zghoBFu-7TXvMC571M"
ADMIN_PASSWORD = "Nahid270"

# ===================== MONGODB =====================

mongo = pymongo.MongoClient(MONGO_URI)
db = mongo["movie_db"]
collection = db["movies"]

# ===================== PYROGRAM BOT =====================

bot = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===================== EXTRACTOR =====================

def extract_info(text):
    pattern = r"(.+?)(?:\\s*\\((\\d{4})\\))?\\s*(?:-|\\s+)?(\\d{3,4}p|HD|SD|FHD)"
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
            poster_path = m.get("poster_path")
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
            overview = m.get("overview", "No overview available.")
            found_year = str(m.get("release_date", '')[:4])
            return {
                "title": m.get("title", title),
                "year": found_year if found_year else year,
                "poster_url": poster_url,
                "overview": overview
            }
    except:
        pass
    return {"title": title, "year": year, "poster_url": "", "overview": "No overview available."}

# ===================== BOT HANDLERS =====================

@bot.on_message(filters.channel & (filters.video | filters.document))
async def save_movie(client, message):
    if not message.caption:
        return
    title, year, quality = extract_info(message.caption)
    if not title or not quality:
        return
    year = year or "Unknown"
    file_id = message.video.file_id if message.video else message.document.file_id
    if not file_id:
        return
    tmdb_data = get_tmdb_info(title, year)
    slug = f"{slugify(tmdb_data['title'])}-{tmdb_data['year']}"
    now = datetime.now()
    existing = collection.find_one({"title": tmdb_data['title'], "year": tmdb_data['year']})
    quality_entry = {"quality": quality, "file_id": file_id}

    if existing:
        found = False
        for q in existing["qualities"]:
            if q["quality"] == quality:
                q.update(quality_entry)
                found = True
        if not found:
            existing["qualities"].append(quality_entry)
        collection.update_one({"_id": existing["_id"]}, {"$set": {
            "qualities": existing["qualities"],
            "poster_url": tmdb_data["poster_url"],
            "overview": tmdb_data["overview"],
            "slug": slug,
            "last_updated": now
        }})
    else:
        collection.insert_one({
            "title": tmdb_data['title'],
            "year": tmdb_data['year'],
            "overview": tmdb_data['overview'],
            "poster_url": tmdb_data['poster_url'],
            "slug": slug,
            "qualities": [quality_entry],
            "created_at": now,
            "last_updated": now
        })

@bot.on_message(filters.private & filters.command("start"))
async def start_cmd(client, message):
    if len(message.command) > 1:
        param = message.command[1]
        file_id = param.split("_")[1]
        if param.startswith("stream_"):
            await client.send_document(message.chat.id, file_id=file_id, caption="📽️ স্ট্রিম করুন")
        elif param.startswith("download_"):
            await client.send_document(message.chat.id, file_id=file_id, caption="📥 ডাউনলোড করুন")
    else:
        await message.reply("🍿 Movie Bot এ স্বাগতম!")

# ===================== FLASK WEBSITE =====================

app = Flask(__name__)
app.secret_key = os.urandom(24)

@app.route("/")
def index():
    movies = list(collection.find().sort("last_updated", -1))
    html = """<h1>🎬 All Movies</h1><ul>"""
    for m in movies:
        html += f'<li><a href="/movie/{m["slug"]}">{m["title"]} ({m["year"]})</a></li>'
    html += "</ul>"
    return html

@app.route("/movie/<slug>")
def movie_detail(slug):
    m = collection.find_one({"slug": slug})
    if not m:
        return "Movie not found", 404
    html = f"""
    <h1>{m['title']} ({m['year']})</h1>
    <p>{m['overview']}</p>
    <img src='{m['poster_url']}' width='200'><br>
    <ul>
    """
    for q in m['qualities']:
        html += f"<li>{q['quality']} - <a href='/watch/{q['file_id']}'>Watch</a> | <a href='/download/{q['file_id']}'>Download</a></li>"
    html += "</ul><a href='/'>⬅️ Back</a>"
    return html

@app.route("/watch/<file_id>")
def watch(file_id):
    return redirect(f"https://t.me/{BOT_USERNAME}?start=stream_{file_id}")

@app.route("/download/<file_id>")
def download(file_id):
    return redirect(f"https://t.me/{BOT_USERNAME}?start=download_{file_id}")

@app.route("/admin", methods=["GET"])
def admin():
    if 'logged_in' in session:
        movies = list(collection.find().sort("last_updated", -1))
        return "<h2>Admin Panel</h2>" + "<br>".join([f"{m['title']} ({m['year']}) <a href='/admin/delete/{m['_id']}'>❌</a>" for m in movies]) + "<br><a href='/admin/logout'>Logout</a>"
    return """<form method='post' action='/admin/login'><input name='password' type='password'><input type='submit'></form>"""

@app.route("/admin/login", methods=["POST"])
def login():
    if request.form.get("password") == ADMIN_PASSWORD:
        session['logged_in'] = True
        return redirect("/admin")
    return "Wrong password"

@app.route("/admin/logout")
def logout():
    session.pop('logged_in', None)
    return redirect("/admin")

@app.route("/admin/delete/<mid>")
def delete_movie(mid):
    if 'logged_in' not in session:
        abort(403)
    collection.delete_one({"_id": ObjectId(mid)})
    return redirect("/admin")

# ===================== RUN BOTH =====================

def run_flask():
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.run()
