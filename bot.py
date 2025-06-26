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
CHANNEL_USERNAME = "autoposht" # আপনার চ্যানেলের ইউজারনেম
BOT_USERNAME = "CtgAutoPostBot" # আপনার বটের ইউজারনেম
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

# ===== Template HTMLs (Unchanged from your original code) =====
INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>MovieZone - All Movies</title>
    <!-- Your existing index HTML -->
</head>
<body>
    <!-- Your existing index body -->
</body>
</html>
"""

MOVIE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>{{ movie.title }}</title>
    <!-- Your existing movie HTML -->
</head>
<body>
    <!-- Your existing movie body -->
</body>
</html>
"""

ADMIN_HTML = """
<!-- Your existing admin HTML -->
"""

LOGIN_HTML = """
<!-- Your existing login HTML -->
"""

# ===== Improved Utility Functions =====
def extract_info(text):
    # Improved regex pattern to handle various title formats
    pattern = r"(.+?)(?:\s*\(?(\d{4})\)?)?(?:\s*\|?\s*(?:HD|HQ)?\s*(\d{3,4}p))?"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        title = match.group(1).strip()
        year = match.group(2) if match.group(2) else "Unknown"
        quality = match.group(3) if match.group(3) else "HD"
        
        # Clean up title (remove unnecessary prefixes/suffixes)
        title = re.sub(r'^(MOVIE|FILM|NEW)\s*[-:]?\s*', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\s*(?:Full Movie|Official|HD|HQ|Complete)\s*$', '', title, flags=re.IGNORECASE)
        
        print(f"Extracted: Title='{title}', Year='{year}', Quality='{quality}'")
        return title, year, quality
    print(f"Failed to extract info from caption: '{text}'")
    return None, None, None

def get_tmdb_info(title, year):
    # First try with original title
    tmdb_data = fetch_tmdb_data(title, year)
    if tmdb_data.get('title'):
        return tmdb_data
    
    # If not found, try cleaning the title further
    cleaned_title = re.sub(r'[^\w\s]', '', title).strip()
    if cleaned_title != title:
        return fetch_tmdb_data(cleaned_title, year)
    
    return {
        "title": title,
        "year": year if year else "Unknown",
        "poster_url": "",
        "overview": "No overview available from TMDB."
    }

def fetch_tmdb_data(title, year):
    search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}"
    if year and year != "0000" and year != "Unknown":
        search_url += f"&year={year}"
    
    try:
        res = requests.get(search_url).json()
        if res.get("results"):
            m = res["results"][0]
            poster_path = m.get('poster_path')
            return {
                "title": m.get('title', title),
                "year": str(m.get('release_date', '')[:4]) if m.get('release_date') else year,
                "poster_url": f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else "",
                "overview": m.get("overview", "No overview available.")
            }
    except Exception as e:
        print(f"TMDB Error: {e}")
    
    return {}

# ===== Pyrogram Bot Handlers =====
@bot.on_message(filters.channel & (filters.video | filters.document))
async def save_movie(client, message):
    if not message.caption:
        return

    title, year, quality = extract_info(message.caption)
    if not title:
        return
    
    file_id = message.video.file_id if message.video else message.document.file_id
    if not file_id:
        return

    tmdb_data = get_tmdb_info(title, year)
    
    movie_slug = f"{slugify(tmdb_data.get('title', title))}-{tmdb_data.get('year', year)}"
    quality_entry = {
        "quality": quality,
        "file_id": file_id,
        "message_id": message.id,
        "added_at": datetime.now()
    }

    existing = collection.find_one({"slug": movie_slug})
    if existing:
        # Update existing movie
        qualities = existing["qualities"]
        # Check if quality already exists
        if not any(q["quality"] == quality for q in qualities):
            qualities.append(quality_entry)
            collection.update_one(
                {"_id": existing["_id"]},
                {"$set": {
                    "qualities": qualities,
                    "last_updated": datetime.now(),
                    "poster_url": tmdb_data.get("poster_url", existing.get("poster_url", ""))
                }}
            )
    else:
        # Insert new movie
        collection.insert_one({
            "title": tmdb_data.get("title", title),
            "year": tmdb_data.get("year", year),
            "language": "Unknown",
            "overview": tmdb_data.get("overview", "No overview available."),
            "poster_url": tmdb_data.get("poster_url", ""),
            "qualities": [quality_entry],
            "slug": movie_slug,
            "created_at": datetime.now(),
            "last_updated": datetime.now()
        })

@bot.on_message(filters.private & filters.command("start"))
async def start_command_handler(client, message):
    if len(message.command) > 1:
        action_param = message.command[1]
        
        if action_param.startswith(("stream_", "download_")):
            action, file_id = action_param.split("_", 1)
            
            try:
                # Find the movie in database
                movie = collection.find_one({"qualities.file_id": file_id})
                if not movie:
                    raise Exception("Movie not found")
                
                # Find the specific quality
                quality = next((q for q in movie["qualities"] if q["file_id"] == file_id), None)
                if not quality:
                    raise Exception("Quality not found")
                
                # Send processing message
                processing_msg = await message.reply_text("📡 ফাইলটি প্রস্তুত করা হচ্ছে...")
                
                # Forward the file with nice caption
                await client.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=CHANNEL_USERNAME,
                    message_id=quality["message_id"],
                    caption=f"🎬 {movie['title']} ({movie['year']})\n"
                           f"📦 Quality: {quality['quality']}\n"
                           f"🔗 {'Watching' if action == 'stream' else 'Download'} Link\n\n"
                           f"👉 @{BOT_USERNAME}"
                )
                
                await processing_msg.delete()
                
            except Exception as e:
                error_msg = await message.reply_text("⚠️ ফাইল লোড করতে সমস্যা হয়েছে। পরে আবার চেষ্টা করুন।")
                await asyncio.sleep(10)
                await error_msg.delete()
    else:
        await message.reply_text(
            "🎥 মুভি ডাউনলোড বা স্ট্রিম করতে আমাদের ওয়েবসাইট ব্যবহার করুন!\n\n"
            f"👉 @{CHANNEL_USERNAME} চ্যানেলে সর্বশেষ মুভি পাবেন"
        )

# ===== Flask App (Unchanged from your original) =====
app = Flask(__name__)
app.secret_key = os.urandom(24)

@app.route("/")
def home():
    movies = list(collection.find().sort("last_updated", -1))
    return render_template_string(INDEX_HTML, movies=movies)

@app.route("/movie/<slug>")
def movie_detail(slug):
    movie = collection.find_one({"slug": slug})
    if not movie:
        abort(404)
    return render_template_string(MOVIE_HTML, movie=movie)

@app.route("/watch/<file_id>")
def watch(file_id):
    return redirect(f"https://t.me/{BOT_USERNAME}?start=stream_{file_id}")

@app.route("/download/<file_id>")
def download(file_id):
    return redirect(f"https://t.me/{BOT_USERNAME}?start=download_{file_id}")

# Admin routes (unchanged from your original)
# ...

def run_flask_app():
    app.run(host="0.0.0.0", port=5000, debug=False)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.start()
    
    print("Starting Telegram Bot...")
    bot.run()
