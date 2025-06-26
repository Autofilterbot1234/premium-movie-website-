import threading
import asyncio
from pyrogram import Client, filters
import pymongo
import re
import requests
from flask import Flask, request, redirect, abort, render_template_string
from slugify import slugify # নিশ্চিত করুন এটি ইনস্টল করা আছে: pip install python-slugify

# ===== CONFIGURATION =====
MONGO_URI = "mongodb+srv://manogog673:manogog673@cluster0.ot1qt.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
TMDB_API_KEY = "7dc544d9253bccc3cfecc1c677f69819"
CHANNEL_USERNAME = "autoposht" # আপনার চ্যানেলের সঠিক ইউজারনেম দিন, যেমন @your_channel
BOT_USERNAME = "CtgAutoPostBot" # আপনার বটের সঠিক ইউজারনেম দিন, যেমন @your_bot
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

# ===== Utility Functions =====
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
                "poster_url": f"https://image.tmdb.org/t/p/w500{m.get('poster_path')}" if m.get('poster_path') else "",
                "overview": m.get("overview", "")
            }
    except Exception as e:
        print(f"Error fetching TMDB info: {e}") # ডিবাগিং এর জন্য এরর প্রিন্ট করা হলো
    return {"poster_url": "", "overview": ""}

# ===== Pyrogram Bot Handler =====
@bot.on_message(filters.channel & (filters.video | filters.document))
async def save_movie(client, message):
    if not message.caption:
        return

    title, year, quality = extract_info(message.caption)
    if not title or not quality:
        print(f"Could not extract info from caption: {message.caption}") # ডিবাগিং এর জন্য
        return

    file_id = message.video.file_id if message.video else message.document.file_id
    tmdb_info = get_tmdb_info(title, year)

    # সিনেমার জন্য একটি ইউনিক স্ল্যাগ তৈরি করুন
    # এখানে বছরের সাথে শিরোনাম যোগ করে স্ল্যাগ তৈরি করা হচ্ছে
    movie_slug = f"{slugify(title)}-{year}"

    # ডেটাবেসে একই টাইটেল এবং সাল এর মুভি আছে কিনা চেক করুন
    existing = collection.find_one({"title": title, "year": year}) 
    # বিকল্প: {"slug": movie_slug} দিয়েও চেক করতে পারেন যদি স্ল্যাগ ইউনিক রাখতে চান

    quality_entry = {"quality": quality, "file_id": file_id}

    if existing:
        # বিদ্যমান মুভির ক্ষেত্রে কোয়ালিটি আপডেট বা যোগ করুন
        quality_found = False
        for q in existing["qualities"]:
            if q["quality"] == quality:
                q.update(quality_entry)
                quality_found = True
                break
        if not quality_found:
            existing["qualities"].append(quality_entry)
        
        # নিশ্চিত করুন যে slug field আছে এবং আপডেটেড (যদি title বা year পরিবর্তন হয়)
        # সাধারণত, একবার যোগ হলে slug পরিবর্তন হয় না, তবুও নিশ্চিত করা ভালো
        existing["slug"] = movie_slug
        collection.update_one({"_id": existing["_id"]}, {"$set": existing})
        print(f"Updated existing movie: {title} ({year})") # ডিবাগিং
    else:
        # নতুন মুভি ডেটাবেসে যোগ করুন
        collection.insert_one({
            "title": title,
            "year": year,
            "language": "Unknown", # আপনার প্রয়োজন অনুযায়ী সেট করুন
            "overview": tmdb_info["overview"],
            "poster_url": tmdb_info["poster_url"],
            "qualities": [quality_entry],
            "slug": movie_slug # এখানে slug সংরক্ষণ করা হচ্ছে
        })
        print(f"Added new movie: {title} ({year})") # ডিবাগিং

# ===== Flask App Setup =====
app = Flask(__name__)

# ===== Flask Routes =====
@app.route("/")
def home():
    movies = list(collection.find())
    # এখানে সিনেমার slug ডেটাবেস থেকে সরাসরি ব্যবহার করা হচ্ছে,
    # তাই নতুন করে slug তৈরির দরকার নেই।
    return render_template_string(INDEX_HTML, movies=movies)

@app.route("/movie/<slug>")
def movie_detail(slug):
    # স্ল্যাগ দিয়ে সরাসরি ডেটাবেসে অনুসন্ধান করুন
    movie = collection.find_one({"slug": slug})
    
    if not movie:
        print(f"Movie not found for slug: {slug}") # ডিবাগিং
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
    try:
        collection.delete_one({"_id": pymongo.ObjectId(mid)})
    except Exception as e:
        print(f"Error deleting movie {mid}: {e}") # ডিবাগিং
        return "Error deleting movie", 500
    return redirect(f"/admin?token={token}")

# ===== RUN BOTH =====
def run_flask_app():
    # Flask অ্যাপকে হোস্ট 0.0.0.0 এ এবং পোর্ট 5000 এ চালান
    # এটি Heroku বা অন্যান্য ক্লাউড প্ল্যাটফর্মে ডেপ্লয় করার জন্য উপযুক্ত।
    # ডিবাগ মোড ডেভেলপমেন্টের জন্য ভালো, প্রোডাকশনের জন্য বন্ধ রাখা উচিত।
    app.run(host="0.0.0.0", port=5000, debug=False)

if __name__ == "__main__":
    # Flask অ্যাপ একটি আলাদা থ্রেডে চালান যাতে বটও সাথে চলতে পারে
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.start()
    
    # টেলিগ্রাম বট চালান
    print("Starting Telegram Bot...")
    bot.run()

