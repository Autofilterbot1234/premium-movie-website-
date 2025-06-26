import threading
import asyncio
from pyrogram import Client, filters
import pymongo
import re
import requests
from flask import Flask, request, redirect, abort, render_template_string, session, url_for
from slugify import slugify # নিশ্চিত করুন এটি ইনস্টল করা আছে: pip install python-slugify
import os # সেশন সিক্রেট কী তৈরি করার জন্য

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

# ===== Template HTMLs =====
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
            max-width: 1000px; /* ম্যাক্সিমাম উইডথ বাড়ানো হয়েছে */
            margin: auto;
            padding: 20px;
            color: #343a40;
            line-height: 1.6;
        }
        h1 {
            text-align: center;
            color: #007bff;
            margin-bottom: 30px;
            font-size: 2.5em; /* ফন্ট সাইজ বাড়ানো হয়েছে */
            font-weight: 700;
        }
        .movies-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); /* মোবাইল: প্রতি সারিতে ২টা কার্ড (কমপক্ষে 160px) */
            gap: 20px; /* গ্যাপ বাড়ানো হয়েছে */
            padding: 0 10px; /* গ্রিডের চারপাশে প্যাডিং */
        }
        .movie-card {
            text-decoration: none;
            color: #343a40;
            background: white;
            border-radius: 12px; /* বর্ডার রেডিয়াস বাড়ানো হয়েছে */
            overflow: hidden;
            box-shadow: 0 8px 20px rgba(0,0,0,0.1); /* শ্যাডো আরও গভীর করা হয়েছে */
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            align-items: center; /* কন্টেন্ট সেন্টারে আনতে */
            padding-bottom: 10px; /* টাইটেলের নিচে প্যাডিং */
        }
        .movie-card:hover {
            transform: translateY(-8px); /* হোভারে আরও উপরে উঠবে */
            box-shadow: 0 12px 25px rgba(0,0,0,0.2);
        }
        .movie-card img {
            width: 100%;
            height: 240px; /* ফিক্সড হাইট, মোবাইল অনুসারে */
            object-fit: cover;
            display: block;
            border-bottom: 1px solid #eee;
        }
        .movie-title {
            padding: 10px 8px; /* প্যাডিং সামঞ্জস্য করা হয়েছে */
            text-align: center;
            font-weight: 600; /* ফন্ট ওয়েট বাড়ানো হয়েছে */
            font-size: 0.95em; /* ফন্ট সাইজ সামঞ্জস্য করা হয়েছে */
            color: #495057;
            flex-grow: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 40px; /* টাইটেল বক্সের মিনিমাম হাইট */
        }

        /* Responsive adjustments */
        @media (max-width: 599px) { /* 600px এর নিচে স্ক্রিনের জন্য (মোবাইল) */
            .movies-grid {
                grid-template-columns: repeat(2, 1fr); /* মোবাইলে প্রতি সারিতে ২টা কার্ড */
                gap: 15px;
            }
            .movie-card img {
                height: 200px; /* মোবাইলে ইমেজের হাইট */
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

        @media (min-width: 600px) and (max-width: 991px) { /* ট্যাবলেট সাইজের জন্য */
            .movies-grid {
                grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); /* প্রতি সারিতে ৩-৪টা কার্ড */
            }
            .movie-card img {
                height: 270px;
            }
        }

        @media (min-width: 992px) { /* ডেস্কটপ স্ক্রিনের জন্য */
            .movies-grid {
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); /* প্রতি সারিতে ৪-৫টা কার্ড */
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
            box-shadow: 0 0 15px rgba(0,0,0,0.05); /* বডির চারপাশে হালকা শ্যাডো */
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
            flex-direction: column; /* মোবাইলের জন্য কলাম লেআউট */
            align-items: center;
            margin-bottom: 25px;
            text-align: center; /* ওভারভিউ টেক্সট সেন্টারে আনতে */
        }
        .movie-content img {
            max-width: 280px; /* মোবাইলের জন্য ইমেজের সাইজ */
            height: auto;
            margin-bottom: 20px;
            border-radius: 10px;
            box-shadow: 0 6px 15px rgba(0,0,0,0.15);
            display: block;
            border: 1px solid #e0e0e0;
        }
        .movie-content p {
            text-align: justify; /* ওভারভিউ টেক্সট জাস্টিফাই করা হয়েছে */
            margin: 0;
            padding: 0 10px; /* সাইড প্যাডিং */
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
            text-align: center; /* কোয়ালিটি টেক্সট সেন্টারে */
        }
        .btn-group {
            display: flex;
            flex-wrap: wrap;
            gap: 12px; /* বাটনগুলির মধ্যে গ্যাপ */
            justify-content: center; /* বাটনগুলোকে সেন্টারে আনতে */
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
        @media (min-width: 600px) { /* 600px এর উপরে স্ক্রিনের জন্য (ডেস্কটপ/ট্যাবলেট) */
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
            color: #dc3545; /* লাল রং অ্যাডমিনের জন্য */
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
            margin-right: 15px; /* টেক্সট এবং বাটনের মধ্যে গ্যাপ */
            font-weight: 500;
        }
        li a {
            color: #dc3545;
            text-decoration: none;
            font-weight: bold;
            padding: 8px 15px;
            border: 2px solid #dc3545; /* বর্ডার মোটা করা হয়েছে */
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
                margin-bottom: 10px; /* নিচে মার্জিন যোগ করা হয়েছে */
                font-size: 0.95em;
            }
            li a {
                align-self: stretch; /* বাটন পুরো প্রস্থে ছড়িয়ে যাবে */
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
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f2f5; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; color: #333; }
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

# ===== Pyrogram Bot Handler for Channel Posts =====
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
    movie_slug = f"{slugify(title)}-{year}"

    # ডেটাবেসে একই টাইটেল এবং সাল এর মুভি আছে কিনা চেক করুন
    existing = collection.find_one({"title": title, "year": year}) 

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

# ===== Pyrogram Bot Handler for /start command =====
@bot.on_message(filters.private & filters.command("start"))
async def start_command_handler(client, message):
    if len(message.command) > 1:
        action_param = message.command[1] 
        
        if action_param.startswith("stream_"):
            file_id = action_param.replace("stream_", "", 1)
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
            await message.reply_text("স্বাগতম! আপনি এখানে আপনার পছন্দের মুভি দেখতে বা ডাউনলোড করতে পারবেন।")
    else:
        await message.reply_text("স্বাগতম! আপনি এখানে আপনার পছন্দের মুভি দেখতে বা ডাউনলোড করতে পারবেন।")


# ===== Flask App Setup =====
app = Flask(__name__)
# সেশন সিক্রেট কী - এটি খুব গুরুত্বপূর্ণ! একটি র্যান্ডম এবং শক্তিশালী কী দিন।
# প্রোডাকশনে এটি এনভায়রনমেন্ট ভেরিয়েবল থেকে আসা উচিত।
app.secret_key = os.urandom(24) # একটি র্যান্ডম সিক্রেট কী তৈরি করবে

# ===== Flask Routes =====
@app.route("/")
def home():
    movies = list(collection.find())
    return render_template_string(INDEX_HTML, movies=movies)

@app.route("/movie/<slug>")
def movie_detail(slug):
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

# অ্যাডমিন লগইন এবং প্যানেল রুট
@app.route("/admin", methods=["GET"])
def admin_panel_or_login():
    if 'logged_in' in session and session['logged_in']:
        movies = list(collection.find())
        return render_template_string(ADMIN_HTML, movies=movies)
    return render_template_string(LOGIN_HTML)

@app.route("/admin/login", methods=["POST"])
def admin_login():
    password = request.form.get("password")
    if password == ADMIN_PASSWORD:
        session['logged_in'] = True
        return redirect(url_for('admin_panel_or_login')) # লগইন সফল হলে অ্যাডমিন প্যানেলে রিডাইরেক্ট
    return render_template_string(LOGIN_HTML, error="Invalid Password")

@app.route("/admin/logout")
def admin_logout():
    session.pop('logged_in', None) # সেশন থেকে লগইন তথ্য মুছে ফেলা
    return redirect(url_for('admin_panel_or_login')) # লগইন পেজে রিডাইরেক্ট

@app.route("/admin/delete/<mid>")
def delete(mid):
    if 'logged_in' not in session or not session['logged_in']:
        return abort(403) # লগইন না থাকলে অ্যাক্সেস Deny
    try:
        from bson.objectid import ObjectId # ObjectId ইম্পোর্ট করুন
        collection.delete_one({"_id": ObjectId(mid)})
    except Exception as e:
        print(f"Error deleting movie {mid}: {e}") # ডিবাগিং
        return "Error deleting movie", 500
    return redirect(url_for('admin_panel_or_login')) # সফলভাবে ডিলিট হলে অ্যাডমিন প্যানেলে রিডাইরেক্ট

# ===== RUN BOTH =====
def run_flask_app():
    # Flask অ্যাপকে হোস্ট 0.0.0.0 এ এবং পোর্ট 5000 এ চালান
    # এটি Heroku বা অন্যান্য ক্লাউড প্ল্যাটফর্মে ডেপ্লয় করার জন্য উপযুক্ত।
    # ডিবাগ মোড ডেভেলপমেন্টের জন্য ভালো, প্রোডাকশনের জন্য বন্ধ রাখা উচিত।
    app.run(host="0.0.0.0", port=5000, debug=False)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.start()
    
    # টেলিগ্রাম বট চালান
    print("Starting Telegram Bot...")
    bot.run()

