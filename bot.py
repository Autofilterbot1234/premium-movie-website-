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
CHANNEL_USERNAME = "autoposht" # আপনার চ্যানেলের সঠিক ইউজারনেম দিন, যেমন @your_channel
BOT_USERNAME = "CtgAutoPostBot" # আপনার বটের সঠিক ইউজারনেম দিন, যেমন @your_bot
API_ID = 22697010
API_HASH = "fd88d7339b0371eb2a9501d523f3e2a7"
BOT_TOKEN = "7347631253:AAFX3dmD0N8q6u0l2zghoBFu-7TXvMC571M"
ADMIN_PASSWORD = "your_strong_admin_password_here" # এখানে আপনার শক্তিশালী অ্যাডমিন পাসওয়ার্ড দিন!

# ===== MongoDB Setup =====
mongo = pymongo.MongoClient(MONGO_URI)
db = mongo["movie_db"]
collection = db["movies"]

# ===== Pyrogram Bot Setup =====
bot = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== Template HTMLs (আগের মতোই আছে, পরিবর্তন করা হয়নি) =====
INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>MovieZone - All Movies</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #e9ecef;
            max-width: 1000px;
            margin: auto;
            padding: 20px;
            color: #343a40;
            line-height: 1.6;
        }
        h1 {
            text-align: center;
            color: #007bff;
            margin-bottom: 30px;
            font-size: 2.5em;
            font-weight: 700;
        }
        .movies-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
            gap: 20px;
            padding: 0 10px;
        }
        .movie-card {
            text-decoration: none;
            color: #343a40;
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 8px 20px rgba(0,0,0,0.1);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 10px;
        }
        .movie-card:hover {
            transform: translateY(-8px);
            box-shadow: 0 12px 25px rgba(0,0,0,0.2);
        }
        .movie-card img {
            width: 100%;
            height: 240px;
            object-fit: cover;
            display: block;
            border-bottom: 1px solid #eee;
        }
        .movie-title {
            padding: 10px 8px;
            text-align: center;
            font-weight: 600;
            font-size: 0.95em;
            color: #495057;
            flex-grow: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 40px;
        }

        /* Responsive adjustments */
        @media (max-width: 599px) {
            .movies-grid {
                grid-template-columns: repeat(2, 1fr);
                gap: 15px;
            }
            .movie-card img {
                height: 200px;
            }
            .movie-title {
                font-size: 0.9em;
            }
            h1 {
                font-size: 2em;
            }
            body {
                padding: 15px;
            }
        }

        @media (min-width: 600px) and (max-width: 991px) {
            .movies-grid {
                grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
            }
            .movie-card img {
                height: 270px;
            }
        }

        @media (min-width: 992px) {
            .movies-grid {
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            }
            .movie-card img {
                height: 300px;
            }
            .movie-title {
                font-size: 1em;
            }
        }
    </style>
</head>
<body>
    <h1>MovieZone - All Movies</h1>
    <div class="movies-grid">
        {% for movie in movies %}
        <a class="movie-card" href="/movie/{{ movie.slug }}">
            <img src="{{ movie.poster_url or 'https://via.placeholder.com/300x450?text=No+Image' }}" alt="{{ movie.title }} Poster">
            <div class="movie-title">{{ movie.title }} ({{ movie.year }})</div>
        </a>
        {% endfor %}
    </div>
</body>
</html>
"""

MOVIE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>{{ movie.title }}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 800px;
            margin: auto;
            padding: 20px;
            background: #ffffff;
            color: #343a40;
            line-height: 1.6;
            box-shadow: 0 0 15px rgba(0,0,0,0.05);
            border-radius: 8px;
        }
        h1 {
            margin-top: 0;
            color: #007bff;
            text-align: center;
            margin-bottom: 25px;
            font-size: 2.2em;
            font-weight: 700;
        }
        .movie-content {
            display: flex;
            flex-direction: column;
            align-items: center;
            margin-bottom: 25px;
            text-align: center;
        }
        .movie-content img {
            max-width: 280px;
            height: auto;
            margin-bottom: 20px;
            border-radius: 10px;
            box-shadow: 0 6px 15px rgba(0,0,0,0.15);
            display: block;
            border: 1px solid #e0e0e0;
        }
        .movie-content p {
            text-align: justify;
            margin: 0;
            padding: 0 10px;
            font-size: 1.05em;
        }
        .quality-section {
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 18px;
            margin-bottom: 15px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }
        .quality-section b {
            display: block;
            margin-bottom: 12px;
            color: #007bff;
            font-size: 1.2em;
            font-weight: 600;
            text-align: center;
        }
        .btn-group {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            justify-content: center;
            margin-top: 15px;
        }
        .btn {
            display: inline-block;
            padding: 12px 25px;
            background: #007bff;
            color: white;
            border-radius: 6px;
            text-decoration: none;
            font-weight: bold;
            transition: background 0.2s, transform 0.2s, box-shadow 0.2s;
            white-space: nowrap;
            box-shadow: 0 4px 10px rgba(0,123,255,0.2);
        }
        .btn:hover {
            background: #0056b3;
            transform: translateY(-3px);
            box-shadow: 0 6px 15px rgba(0,123,255,0.3);
        }
        .back-link {
            display: block;
            text-align: center;
            margin-top: 35px;
            font-size: 1.15em;
            color: #6c757d;
            text-decoration: none;
            font-weight: 600;
            transition: color 0.2s;
        }
        .back-link:hover {
            color: #007bff;
            text-decoration: underline;
        }
        
        /* Responsive adjustments */
        @media (min-width: 600px) {
            h1 {
                text-align: left;
            }
            .movie-content {
                flex-direction: row;
                align-items: flex-start;
                text-align: left;
            }
            .movie-content img {
                max-width: 300px;
                margin-right: 30px;
                margin-bottom: 0;
            }
            .movie-content p {
                padding: 0;
            }
            .quality-section b {
                text-align: left;
            }
            .btn-group {
                justify-content: flex-start;
            }
        }
    </style>
</head>
<body>
    <h1>{{ movie.title }} ({{ movie.year }})</h1>
    <div class="movie-content">
        <img src="{{ movie.poster_url or 'https://via.placeholder.com/300x450?text=No+Image' }}" alt="{{ movie.title }} Poster">
        <p>{{ movie.overview }}</p>
    </div>
    
    {% for q in movie.qualities %}
    <div class="quality-section">
        <b>{{ q.quality }}</b>
        <div class="btn-group">
            <a class="btn" href="/watch/{{ q.file_id }}">▶️ Watch</a>
            <a class="btn" href="/download/{{ q.file_id }}">⬇️ Download</a>
        </div>
    </div>
    {% endfor %}
    <a href="/" class="back-link">← Back to All Movies</a>
</body>
</html>
"""

ADMIN_HTML = """
<html>
<head>
    <title>Admin Panel</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 800px;
            margin: auto;
            padding: 20px;
            background: #f8f9fa;
            color: #343a40;
        }
        h1 {
            text-align: center;
            color: #dc3545;
            margin-bottom: 30px;
            font-size: 2.2em;
            font-weight: 700;
        }
        ul {
            list-style: none;
            padding: 0;
        }
        li {
            background: white;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            margin-bottom: 12px;
            padding: 18px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 10px rgba(0,0,0,0.05);
            font-size: 1.05em;
        }
        li span {
            flex-grow: 1;
            margin-right: 15px;
            font-weight: 500;
        }
        li a {
            color: #dc3545;
            text-decoration: none;
            font-weight: bold;
            padding: 8px 15px;
            border: 2px solid #dc3545;
            border-radius: 5px;
            transition: background 0.2s, color 0.2s, transform 0.2s;
            white-space: nowrap;
        }
        li a:hover {
            background: #dc3545;
            color: white;
            transform: translateY(-2px);
        }
        .logout-btn {
            display: block;
            margin: 20px auto;
            padding: 10px 20px;
            background: #6c757d;
            color: white;
            text-align: center;
            border-radius: 5px;
            text-decoration: none;
            font-weight: bold;
            max-width: 150px;
            transition: background 0.2s;
        }
        .logout-btn:hover {
            background: #5a6268;
        }
        /* Responsive adjustments */
        @media (max-width: 600px) {
            body {
                padding: 15px;
            }
            li {
                flex-direction: column;
                align-items: flex-start;
                padding: 15px;
            }
            li span {
                margin-right: 0;
                margin-bottom: 10px;
                font-size: 0.95em;
            }
            li a {
                align-self: stretch;
                text-align: center;
            }
        }
    </style>
</head>
<body>
    <h1>Admin Panel</h1>
    <ul>
        {% for movie in movies %}
        <li>
            <span>{{ movie.title }} ({{ movie.year }})</span>
            <a href='{{ url_for("delete", mid=movie._id) }}'>❌ Delete</a>
        </li>
        {% endfor %}
    </ul>
    <a href="{{ url_for('admin_logout') }}" class="logout-btn">Logout</a>
</body>
</html>
"""

LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Admin Login</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f2f5; display: flex; justify-content: center; align-items: center; min-height: 10vh; margin: 0; color: #333; }
        .login-container { background: white; padding: 40px; border-radius: 10px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); text-align: center; max-width: 400px; width: 90%; }
        h1 { color: #007bff; margin-bottom: 25px; font-size: 2em; }
        input[type="password"] { width: calc(100% - 20px); padding: 12px; margin-bottom: 20px; border: 1px solid #ddd; border-radius: 5px; font-size: 1em; }
        button { background: #007bff; color: white; padding: 12px 25px; border: none; border-radius: 5px; cursor: pointer; font-size: 1.1em; font-weight: bold; transition: background 0.3s ease; }
        button:hover { background: #0056b3; }
        .error-message { color: #dc3545; margin-top: 15px; font-weight: bold; }
    </style>
</head>
<body>
    <div class="login-container">
        <h1>Admin Login</h1>
        <form action="{{ url_for('admin_login') }}" method="post">
            <input type="password" name="password" placeholder="Enter Admin Password" required>
            <button type="submit">Login</button>
        </form>
        {% if error %}
            <p class="error-message">{{ error }}</p>
        {% endif %}
    </div>
</body>
</html>
"""


# ===== Utility Functions =====
def extract_info(text):
    # Updated regex to be more robust for year extraction
    # It tries to find a 4-digit number (year) optionally, and then 3/4p
    pattern = r"(.+?)(?:\s*\(?(\d{4})\)?)?\s*(?:\||-|–|\s+)?(\d{3,4}p)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        title = match.group(1).strip()
        year = match.group(2) # সাল পাওয়া গেলে সেটি, না পেলে None
        quality = match.group(3)
        print(f"Extracted: Title='{title}', Year='{year}', Quality='{quality}'")
        return title, year, quality
    print(f"Failed to extract info from caption: '{text}' (No title, year, or quality pattern matched)")
    return None, None, None

def get_tmdb_info(title, year):
    # TMDB সার্চের জন্য সঠিক বছর ব্যবহার করুন, যদি না থাকে তবে শুধু টাইটেল দিয়ে সার্চ করুন
    search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}"
    if year and year != "0000": # '0000' যদি ডিফল্ট হিসেবে আসে সেটা এড়িয়ে যান
        search_url += f"&year={year}"
    
    print(f"Fetching TMDB info for: {title} ({year if year else 'No Year'}) from URL: {search_url}")

    try:
        res = requests.get(search_url).json()
        print(f"TMDB API Response: {res}")

        if res.get("results"):
            # প্রথম সেরা ফলাফলটি নিন
            m = res["results"][0]
            poster_path = m.get('poster_path')
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
            overview = m.get("overview", "No overview available.") # ডিফল্ট টেক্সট যোগ করা হয়েছে
            
            # নিশ্চিত করুন যে বছর সঠিক
            found_year = str(m.get('release_date', '')[:4])
            if not year and found_year: # যদি ক্যাপশনে বছর না থাকে, কিন্তু TMDB তে পাওয়া যায়
                year = found_year
            elif year and found_year and year != found_year: # যদি ক্যাপশনের বছর TMDB এর সাথে না মেলে
                print(f"Warning: Year mismatch for '{title}'. Caption year: {year}, TMDB year: {found_year}")
                # আপনি চাইলে এখানে TMDB এর বছরটিকে গ্রহণ করতে পারেন, অথবা ক্যাপশনের বছরটিই রাখতে পারেন
                # আপাতত, ক্যাপশনের বছরই অগ্রাধিকার পাচ্ছে, তবে এটি একটি চিন্তার বিষয়।
                # এই উদাহরনে আমরা TMDB এর বছরটিকেই ব্যবহার করছি যদি এটি আরও নির্ভরযোগ্য হয়।
                year = found_year


            print(f"TMDB Success: Title='{m.get('title')}', Year='{year}', Poster URL='{poster_url}', Overview='{overview[:50]}...'")
            return {
                "title": m.get('title', title), # TMDB টাইটেল ব্যবহার করুন যদি পাওয়া যায়
                "year": year,
                "poster_url": poster_url,
                "overview": overview
            }
        else:
            print(f"TMDB No results found for: {title} ({year if year else 'No Year'})")
    except Exception as e:
        print(f"Error fetching TMDB info for {title} ({year if year else 'No Year'}): {e}")
    
    # যদি TMDB থেকে কোনো তথ্য না আসে, তবে ডিফল্ট খালি তথ্য ফেরত দিন
    return {"title": title, "year": year if year else "Unknown", "poster_url": "", "overview": "No overview available from TMDB."}


# ===== Pyrogram Bot Handler for Channel Posts =====
@bot.on_message(filters.channel & (filters.video | filters.document))
async def save_movie(client, message):
    print(f"Received message in channel: {message.chat.id}")
    if not message.caption:
        print("Message has no caption, skipping.")
        return

    title, year, quality = extract_info(message.caption)
    if not title or not quality:
        print(f"Could not extract info (title/quality) from caption: '{message.caption}', skipping.")
        return
    
    # যদি বছর None আসে, '0000' হিসেবে সেট করুন বা একটি খালি স্ট্রিং
    # TMDB ফাংশন এটি ম্যানেজ করবে
    if year is None:
        year = "Unknown" # বা আপনি একটি ডিফল্ট বছর সেট করতে পারেন

    file_id = None
    if message.video:
        file_id = message.video.file_id
        print(f"Detected video, file_id: {file_id}")
    elif message.document:
        file_id = message.document.file_id
        print(f"Detected document, file_id: {file_id}")
    
    if not file_id:
        print("No video or document file_id found, skipping.")
        return

    # TMDB থেকে বিস্তারিত তথ্য আনুন
    tmdb_data = get_tmdb_info(title, year)
    
    # নিশ্চিত করুন যে tmdb_data একটি ডিকশনারি এবং তাতে প্রয়োজনীয় কী আছে
    # যদি TMDB থেকে title/year পরিবর্তন হয়ে আসে, তাহলে সেটাই ব্যবহার করুন
    actual_title = tmdb_data.get("title", title)
    actual_year = tmdb_data.get("year", year)
    poster_url = tmdb_data.get("poster_url", "")
    overview = tmdb_data.get("overview", "No overview available.")

    movie_slug = f"{slugify(actual_title)}-{actual_year}"
    print(f"Generated slug: {movie_slug}")

    current_time = datetime.now() 

    existing = collection.find_one({"title": actual_title, "year": actual_year}) 

    quality_entry = {"quality": quality, "file_id": file_id}

    if existing:
        print(f"Found existing movie: {existing['title']} ({existing['year']})")
        quality_found = False
        for q in existing["qualities"]:
            if q["quality"] == quality:
                q.update(quality_entry)
                quality_found = True
                print(f"Updated quality {quality} for existing movie.")
                break
        if not quality_found:
            existing["qualities"].append(quality_entry)
            print(f"Added new quality {quality} to existing movie.")
        
        # নিশ্চিত করুন যে সকল TMDB ডেটা আপডেট হচ্ছে
        collection.update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "title": actual_title, # TMDB থেকে আসা আপডেটেড টাইটেল
                "year": actual_year,   # TMDB থেকে আসা আপডেটেড বছর
                "overview": overview,
                "poster_url": poster_url,
                "qualities": existing["qualities"], # কোয়ালিটি লিস্ট আপডেট সহ
                "slug": movie_slug,
                "last_updated": current_time 
            }}
        )
        print(f"Finished updating movie: {actual_title} ({actual_year}) with TMDB info.")
    else:
        print(f"Adding new movie: {actual_title} ({actual_year})")
        collection.insert_one({
            "title": actual_title,
            "year": actual_year,
            "language": "Unknown", # আপনার প্রয়োজন অনুযায়ী সেট করুন
            "overview": overview,
            "poster_url": poster_url,
            "qualities": [quality_entry],
            "slug": movie_slug,
            "created_at": current_time,
            "last_updated": current_time
        })
        print(f"Finished adding new movie: {actual_title} ({actual_year}) with TMDB info.")

# ===== Pyrogram Bot Handler for /start command =====
@bot.on_message(filters.private & filters.command("start"))
async def start_command_handler(client, message):
    print(f"Received /start command from {message.from_user.id}")
    if len(message.command) > 1:
        action_param = message.command[1] 
        print(f"Start command parameter: {action_param}")
        
        if action_param.startswith("stream_"):
            file_id = action_param.replace("stream_", "", 1)
            print(f"Action: Stream, File ID: {file_id}")
            try:
                await client.send_document(
                    chat_id=message.chat.id,
                    file_id=file_id,
                    caption="আপনার অনুরোধ করা ফাইলটি এখানে! 🍿\n\nযদি এটি ভিডিও হয়, তাহলে আপনি এটি স্ট্রিম করতে পারবেন।"
                )
                print(f"Sent stream file {file_id} to {message.chat.id}")
            except Exception as e:
                await message.reply_text(f"দুঃখিত, ফাইলটি স্ট্রিম করা যায়নি। অনুগ্রহ করে পরে আবার চেষ্টা করুন। এরর: {e}")
                print(f"Error sending stream file {file_id}: {e}")

        elif action_param.startswith("download_"):
            file_id = action_param.replace("download_", "", 1)
            print(f"Action: Download, File ID: {file_id}")
            try:
                await client.send_document(
                    chat_id=message.chat.id,
                    file_id=file_id,
                    caption="আপনার অনুরোধ করা ফাইলটি এখানে! 📥\n\nআপনি এটি ডাউনলোড করতে পারবেন।"
                )
                print(f"Sent download file {file_id} to {message.chat.id}")
            except Exception as e:
                await message.reply_text(f"দুঃখিত, ফাইলটি ডাউনলোড করা যায়নি। অনুগ্রহ করে পরে আবার চেষ্টা করুন। এরর: {e}")
                print(f"Error sending download file {file_id}: {e}")
        else:
            print(f"Unknown start command parameter: {action_param}")
            await message.reply_text("স্বাগতম! আপনি এখানে আপনার পছন্দের মুভি দেখতে বা ডাউনলোড করতে পারবেন।")
    else:
        print("Received /start command without parameter.")
        await message.reply_text("স্বাগতম! আপনি এখানে আপনার পছন্দের মুভি দেখতে বা ডাউনলোড করতে পারবেন।")


# ===== Flask App Setup =====
app = Flask(__name__)
app.secret_key = os.urandom(24)

# ===== Flask Routes =====
@app.route("/")
def home():
    movies = list(collection.find().sort([("last_updated", pymongo.DESCENDING), ("created_at", pymongo.DESCENDING)]))
    print(f"Loaded {len(movies)} movies for home page, sorted by latest.")
    return render_template_string(INDEX_HTML, movies=movies)

@app.route("/movie/<slug>")
def movie_detail(slug):
    movie = collection.find_one({"slug": slug})
    
    if not movie:
        print(f"Movie not found for slug: {slug}")
        return abort(404)
    
    print(f"Displaying movie detail for: {movie.get('title')} (Slug: {slug})")
    return render_template_string(MOVIE_HTML, movie=movie)

@app.route("/watch/<file_id>")
def watch(file_id):
    redirect_url = f"https://t.me/{BOT_USERNAME}?start=stream_{file_id}"
    print(f"Redirecting to watch URL: {redirect_url}")
    return redirect(redirect_url)

@app.route("/download/<file_id>")
def download(file_id):
    redirect_url = f"https://t.me/{BOT_USERNAME}?start=download_{file_id}"
    print(f"Redirecting to download URL: {redirect_url}")
    return redirect(redirect_url)

# অ্যাডমিন লগইন এবং প্যানেল রুট
@app.route("/admin", methods=["GET"])
def admin_panel_or_login():
    if 'logged_in' in session and session['logged_in']:
        movies = list(collection.find().sort([("last_updated", pymongo.DESCENDING), ("created_at", pymongo.DESCENDING)]))
        print("Admin logged in, displaying admin panel.")
        return render_template_string(ADMIN_HTML, movies=movies)
    print("Admin not logged in, displaying login page.")
    return render_template_string(LOGIN_HTML)

@app.route("/admin/login", methods=["POST"])
def admin_login():
    password = request.form.get("password")
    print(f"Attempting admin login with password: {'*' * len(password)}")
    if password == ADMIN_PASSWORD:
        session['logged_in'] = True
        print("Admin login successful.")
        return redirect(url_for('admin_panel_or_login'))
    print("Admin login failed: Invalid Password.")
    return render_template_string(LOGIN_HTML, error="Invalid Password")

@app.route("/admin/logout")
def admin_logout():
    session.pop('logged_in', None)
    print("Admin logged out.")
    return redirect(url_for('admin_panel_or_login'))

@app.route("/admin/delete/<mid>")
def delete(mid):
    if 'logged_in' not in session or not session['logged_in']:
        print("Unauthorized attempt to delete movie.")
        return abort(403)
    try:
        print(f"Attempting to delete movie with ID: {mid}")
        collection.delete_one({"_id": ObjectId(mid)})
        print(f"Successfully deleted movie with ID: {mid}")
    except Exception as e:
        print(f"Error deleting movie {mid}: {e}")
        return "Error deleting movie", 500
    return redirect(url_for('admin_panel_or_login'))

# ===== RUN BOTH =====
def run_flask_app():
    print("Starting Flask app...")
    app.run(host="0.0.0.0", port=5000, debug=False)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.start()
    
    print("Starting Telegram Bot...")
    bot.run()
