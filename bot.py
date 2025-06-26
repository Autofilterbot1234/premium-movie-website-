import threading
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import pymongo
import re
import requests
from flask import Flask, request, redirect, abort, render_template_string, session, url_for
from slugify import slugify
import os
from bson.objectid import ObjectId
from datetime import datetime
import logging
from dotenv import load_dotenv

# --- Load Environment Variables ---
load_dotenv() # Load environment variables from .env file

MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://manogog673:manogog673@cluster0.ot1qt.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "7dc544d9253bccc3cfecc1c677f69819")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "autoposht")
BOT_USERNAME = os.getenv("BOT_USERNAME", "CtgAutoPostBot")
API_ID = int(os.getenv("API_ID", "22697010"))
API_HASH = os.getenv("API_HASH", "fd88d7339b0371eb2a9501d523f3e2a7")
BOT_TOKEN = os.getenv("BOT_TOKEN", "7347631253:AAFX3dmD0N8q6u0l2zghoBFu-7TXvMC571M")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Nahid270")

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- MongoDB Setup ---
try:
    mongo = pymongo.MongoClient(MONGO_URI)
    db = mongo["movie_db"]
    collection = db["movies"]
    collection.create_index([("title", pymongo.ASCENDING), ("year", pymongo.ASCENDING)])
    collection.create_index("slug", unique=True)
    logger.info("MongoDB connection successful and indexes ensured.")
except pymongo.errors.ConnectionFailure as e:
    logger.error(f"Could not connect to MongoDB: {e}")
    exit(1)

# --- Pyrogram Bot Setup ---
try:
    bot = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
    logger.info("Pyrogram bot client initialized.")
except Exception as e:
    logger.error(f"Failed to initialize Pyrogram bot: {e}")
    exit(1)

# --- Utility Functions ---
def extract_info(text):
    pattern = r"(.+?)(?:\s*\((\d{4})\))?\s*(?:\[|\(|\s|-)?(?:(\d{3,4}p|HD|SD|FHD|WEB-DL|BluRay|X264|X265|HDRIP|BRRIP|WEBRip|AVC|xvid)\b[^\]\)\s]*)*(?:\]|\)|\s|-)?(?:.*)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        title = match.group(1).strip()
        year = match.group(2) or "Unknown"
        quality_match = re.findall(r"(\d{3,4}p|HD|SD|FHD|WEB-DL|BluRay|X264|X265|HDRIP|BRRIP|WEBRip|AVC|xvid)", text, re.IGNORECASE)
        quality = ", ".join(sorted(list(set(q.upper() for q in quality_match)))) if quality_match else "Unknown"
        return title, year, quality
    logger.warning(f"Could not extract info from caption: {text}")
    return text.strip(), "Unknown", "Unknown"

def get_tmdb_info(title, year):
    try:
        url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}"
        if year != "Unknown":
            url += f"&year={year}"
        res = requests.get(url).json()
        if res.get("results"):
            m = res["results"][0]
            # Using a fallback public placeholder for images in single-file version
            poster = f"https://image.tmdb.org/t/p/w500{m['poster_path']}" if m.get('poster_path') else "https://via.placeholder.com/200x300.png?text=No+Poster"
            overview = m.get("overview", "No overview available.")
            tmdb_title = m.get("title", title)
            tmdb_year = m.get("release_date", "")[:4] or year
            logger.info(f"TMDB found: {tmdb_title} ({tmdb_year})")
            return {
                "title": tmdb_title,
                "year": tmdb_year,
                "poster_url": poster,
                "overview": overview
            }
        else:
            logger.info(f"No TMDB results for '{title}' ({year}).")
    except requests.exceptions.RequestException as e:
        logger.error(f"TMDB API request failed for '{title}': {e}")
    except ValueError as e:
        logger.error(f"TMDB API response JSON decode error for '{title}': {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during TMDB lookup for '{title}': {e}")
    return {"title": title, "year": year, "poster_url": "https://via.placeholder.com/200x300.png?text=No+Poster", "overview": "No overview available."}

# --- Bot Handler ---
@bot.on_message(filters.channel & (filters.video | filters.document))
async def save_movie(client, message):
    if not message.caption:
        logger.info(f"Skipping message {message.id} from channel due to no caption.")
        return

    if message.chat.username and message.chat.username.lower() != CHANNEL_USERNAME.lower():
        logger.info(f"Skipping message {message.id} from unexpected channel @{message.chat.username}. Expected @{CHANNEL_USERNAME}")
        return

    title, year, quality = extract_info(message.caption)
    file_id = message.video.file_id if message.video else message.document.file_id
    file_name = message.video.file_name if message.video else message.document.file_name
    file_size = message.video.file_size if message.video else message.document.file_size

    tmdb = get_tmdb_info(title, year)
    slug = slugify(f"{tmdb['title']}-{tmdb['year']}") if tmdb['year'] != "Unknown" else slugify(tmdb['title'])
    now = datetime.now()

    quality_entry = {
        "quality": quality,
        "file_id": file_id,
        "file_name": file_name,
        "file_size": file_size,
        "uploaded_at": now
    }

    try:
        result = collection.find_one_and_update(
            {"slug": slug},
            {
                "$set": {
                    "title": tmdb['title'],
                    "year": tmdb['year'],
                    "overview": tmdb['overview'],
                    "poster_url": tmdb['poster_url'],
                    "last_updated": now
                },
                "$addToSet": {
                    "qualities": quality_entry
                },
                "$setOnInsert": {
                    "created_at": now
                }
            },
            upsert=True,
            return_document=pymongo.ReturnDocument.AFTER
        )
        logger.info(f"Movie '{tmdb['title']} ({tmdb['year']})' saved/updated in DB with quality '{quality}'.")
    except Exception as e:
        logger.error(f"Error saving/updating movie '{tmdb['title']}': {e}")


@bot.on_message(filters.private & filters.command("start"))
async def start_command(client, message):
    current_host_url = request.host_url # This works because Flask context is available here.
    if len(message.command) > 1:
        command_arg = message.command[1]
        logger.info(f"Received /start command with argument: {command_arg} from user {message.from_user.id}")

        if command_arg.startswith("stream_") or command_arg.startswith("download_"):
            file_id = command_arg.split("_", 1)[1]
            try:
                movie = collection.find_one({"qualities.file_id": file_id})
                movie_title = movie['title'] if movie else "the requested movie"
                movie_year = movie['year'] if movie else ""

                await client.send_document(
                    chat_id=message.chat.id,
                    document=file_id,
                    caption=f"Here is your movie: **{movie_title} ({movie_year})**!\n\nTo get it again or share, use the link below:",
                    parse_mode="Markdown"
                )
                await message.reply_text(
                    "Your movie has been sent! You can also click the button below to get it again, or visit our website.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Get Movie Again", url=f"https://t.me/{BOT_USERNAME}?start={command_arg}")],
                        [InlineKeyboardButton("Visit Website", url=current_host_url)]
                    ])
                )
                logger.info(f"Sent movie file_id {file_id} to user {message.from_user.id}.")
            except Exception as e:
                logger.error(f"Error sending file_id {file_id} to user {message.from_user.id}: {e}")
                await message.reply_text(f"Sorry, I couldn't find that movie file. It might have been deleted or is unavailable. Please check the website. Error: {e}")
        else:
            await message.reply_text(
                "Welcome! Send me a movie caption from your channel to save it. \n\nVisit our website to browse movies:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Browse Movies", url=current_host_url)]
                ])
            )
    else:
        await message.reply_text(
            "Hello! I'm your movie auto-posting bot. I save movies from your channel to a database and make them available on a website. \n\nTo browse movies, visit our website:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Browse Movies", url=current_host_url)]
            ])
        )
    logger.info(f"Handled /start command from user {message.from_user.id}.")

# --- Flask Setup ---
app = Flask(__name__)
app.secret_key = os.urandom(24)
logger.info("Flask app initialized.")

# --- HTML Templates (as Python strings) ---
INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>All Movies - Your Movie Site</title>
    <style>
        /* CSS styles directly embedded */
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #eef2f7; color: #333; line-height: 1.6; }
        .container { max-width: 1200px; margin: 20px auto; padding: 0 15px; }
        header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; padding-bottom: 10px; border-bottom: 1px solid #ddd; }
        header h1 { color: #2c3e50; margin: 0; font-size: 2.2em; }
        .admin-link { text-decoration: none; background-color: #3498db; color: white; padding: 10px 15px; border-radius: 5px; font-weight: bold; transition: background-color 0.3s ease; }
        .admin-link:hover { background-color: #2980b9; }
        .movie-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 20px; margin-top: 20px; }
        .movie-card { background-color: #fff; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); overflow: hidden; text-align: center; transition: transform 0.2s ease, box-shadow 0.2s ease; }
        .movie-card:hover { transform: translateY(-5px); box-shadow: 0 6px 20px rgba(0,0,0,0.15); }
        .movie-card a { text-decoration: none; color: inherit; display: block; }
        .poster-container { width: 100%; height: 240px; overflow: hidden; background-color: #f0f0f0; display: flex; align-items: center; justify-content: center; }
        .movie-poster { width: 100%; height: 100%; object-fit: cover; border-top-left-radius: 10px; border-top-right-radius: 10px; }
        .movie-info { padding: 10px; background-color: #f9f9f9; border-top: 1px solid #eee; }
        .movie-card h3 { font-size: 1.1em; margin: 0 0 5px 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #333; }
        .movie-year { font-size: 0.9em; color: #666; }
        .no-movies-message { grid-column: 1 / -1; text-align: center; font-size: 1.2em; color: #777; padding: 50px; background-color: #fff; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        @media (min-width: 768px) {
            .movie-grid { grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); }
            .poster-container { height: 300px; }
            .movie-card h3 { font-size: 1.2em; }
        }
        @media (min-width: 1200px) {
            .movie-grid { grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }
            .poster-container { height: 330px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>All Movies</h1>
            <a href='/admin' class="admin-link">Admin Panel</a>
        </header>
        <div class="movie-grid">
            {% for movie in movies %}
            <div class="movie-card">
                <a href='/movie/{{movie.slug}}'>
                    <div class="poster-container">
                        <img src="{{ movie.poster_url if movie.poster_url else 'https://via.placeholder.com/200x300.png?text=No+Poster' }}" alt="{{ movie.title }}" class="movie-poster">
                    </div>
                    <div class="movie-info">
                        <h3>{{movie.title}}</h3>
                        <p class="movie-year">({{movie.year}})</p>
                    </div>
                </a>
            </div>
            {% endfor %}
            {% if not movies %}
                <p class="no-movies-message">No movies found yet. Post some movies to your Telegram channel!</p>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

MOVIE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ movie.title }} ({{ movie.year }}) - Details</title>
    <style>
        /* CSS styles directly embedded */
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #eef2f7; color: #333; line-height: 1.6; }
        .container { max-width: 1200px; margin: 20px auto; padding: 0 15px; }
        .back-button { display: inline-block; margin-bottom: 25px; text-decoration: none; color: #007bff; font-weight: bold; font-size: 1.1em; transition: color 0.3s ease; }
        .back-button:hover { color: #0056b3; }
        .movie-detail { background-color: #fff; padding: 25px; border-radius: 10px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); display: flex; flex-direction: column; align-items: center; }
        .detail-poster-container { width: 280px; height: 420px; overflow: hidden; border-radius: 8px; margin-bottom: 25px; box-shadow: 0 2px 10px rgba(0,0,0,0.2); }
        .detail-poster { width: 100%; height: 100%; object-fit: cover; }
        .detail-content { text-align: center; flex: 1; }
        .detail-content h1 { font-size: 2em; margin-top: 0; color: #2c3e50; }
        .detail-content .overview { line-height: 1.8; text-align: left; color: #555; margin-top: 15px; margin-bottom: 25px; }
        .detail-content h2 { font-size: 1.5em; color: #2c3e50; border-bottom: 1px solid #eee; padding-bottom: 10px; margin-bottom: 20px; }
        .qualities { margin-top: 20px; display: flex; flex-direction: column; gap: 15px; align-items: center; }
        .quality-item { background-color: #f0f8ff; padding: 15px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); display: flex; flex-direction: column; align-items: center; gap: 10px; width: 100%; max-width: 300px; }
        .quality-text { font-weight: bold; font-size: 1.1em; color: #34495e; }
        .file-size { font-size: 0.9em; color: #7f8c8d; }
        .quality-buttons { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }
        .btn { display: inline-block; padding: 10px 20px; border-radius: 5px; text-decoration: none; color: #fff; font-weight: bold; transition: background-color 0.3s ease, transform 0.1s ease; text-align: center; min-width: 120px; }
        .btn:active { transform: translateY(1px); }
        .btn-watch { background-color: #28a745; }
        .btn-watch:hover { background-color: #218838; }
        .btn-download { background-color: #007bff; }
        .btn-download:hover { background-color: #0056b3; }
        @media (min-width: 768px) {
            .movie-detail { flex-direction: row; text-align: left; }
            .detail-poster-container { margin-right: 40px; margin-bottom: 0; width: 300px; height: 450px; }
            .detail-content { text-align: left; }
            .detail-content h1 { font-size: 2.5em; }
            .qualities { flex-direction: row; justify-content: flex-start; flex-wrap: wrap; }
            .quality-item { flex-direction: row; justify-content: space-between; gap: 20px; max-width: none; width: auto; }
            .quality-buttons { flex-wrap: nowrap; }
        }
    </style>
</head>
<body>
    <div class="container">
        <a href='/' class="back-button">⬅ Back to All Movies</a>
        <div class="movie-detail">
            <div class="detail-poster-container">
                <img src='{{ movie.poster_url if movie.poster_url else "https://via.placeholder.com/200x300.png?text=No+Poster" }}' alt="{{ movie.title }}" class="detail-poster" />
            </div>
            <div class="detail-content">
                <h1>{{ movie.title }} <span class="movie-year">({{ movie.year }})</span></h1>
                <p class="overview">{{ movie.overview }}</p>
                <h2>Available Qualities:</h2>
                <div class="qualities">
                    {% for q in movie.qualities %}
                    <div class="quality-item">
                        <span class="quality-text">{{q.quality}}</span>
                        <span class="file-size">({{ "%.2f MB" | format(q.file_size / (1024*1024)) if q.file_size else "N/A" }})</span>
                        <div class="quality-buttons">
                            <a href='/watch/{{q.file_id}}' class="btn btn-watch">Watch Online</a>
                            <a href='/download/{{q.file_id}}' class="btn btn-download">Download</a>
                        </div>
                    </div>
                    {% endfor %}
                </div>
            </div>
        </div>
    </div>
</body>
</html>
"""

LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Login</title>
    <style>
        /* CSS styles directly embedded */
        body { display: flex; justify-content: center; align-items: center; min-height: 100vh; background-color: #f4f4f4; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        .login-container { background-color: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; width: 90%; max-width: 400px; }
        .login-container h2 { margin-bottom: 25px; color: #333; }
        .login-container input { width: calc(100% - 20px); padding: 10px; margin-bottom: 15px; border: 1px solid #ddd; border-radius: 5px; font-size: 1em; }
        .login-container button { background-color: #007bff; color: white; padding: 12px 25px; border: none; border-radius: 5px; cursor: pointer; font-size: 1.1em; transition: background-color 0.3s ease; }
        .login-container button:hover { background-color: #0056b3; }
        .login-container p { color: #dc3545; margin-top: 15px; font-weight: bold; }
    </style>
</head>
<body>
    <div class="login-container">
        <h2>Admin Login</h2>
        <form method='post' action="/admin">
            <input name='password' type='password' placeholder="Admin Password" required/>
            <button type='submit'>Login</button>
            {% if error %}<p>{{error}}</p>{% endif %}
        </form>
    </div>
</body>
</html>
"""

ADMIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Panel</title>
    <style>
        /* CSS styles directly embedded */
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #eef2f7; color: #333; line-height: 1.6; }
        .container { max-width: 1200px; margin: 20px auto; padding: 0 15px; }
        .admin-panel { background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .admin-panel h1 { color: #333; margin-bottom: 20px; }
        .admin-panel ul { list-style: none; padding: 0; margin-top: 20px; }
        .admin-panel li { padding: 12px 0; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; font-size: 1.1em; }
        .admin-panel li:last-child { border-bottom: none; }
        .admin-panel li span { flex-grow: 1; margin-right: 15px; }
        .admin-panel li a { color: #dc3545; text-decoration: none; font-weight: bold; padding: 5px 10px; border-radius: 4px; transition: background-color 0.3s ease; }
        .admin-panel li a:hover { background-color: #f8d7da; }
        .admin-logout { display: inline-block; margin-top: 10px; padding: 10px 18px; background-color: #6c757d; color: white; text-decoration: none; border-radius: 5px; transition: background-color 0.3s ease; }
        .admin-logout:hover { background-color: #5a6268; }
        .no-movies-message { text-align: center; font-size: 1.2em; color: #777; padding: 20px 0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="admin-panel">
            <h1>Admin Panel</h1>
            <a href='/admin/logout' class="admin-logout">Logout</a>
            <ul>
                {% for movie in movies %}
                <li>
                    <span>{{movie.title}} ({{movie.year}})</span>
                    <a href='/admin/delete/{{movie._id}}' onclick="return confirm('Are you sure you want to delete {{movie.title}}?');">Delete</a>
                </li>
                {% endfor %}
            </ul>
            {% if not movies %}
                <p class="no-movies-message">No movies found in the database.</p>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""

# --- Flask Routes ---
@app.route("/")
def home():
    movies = list(collection.find().sort("last_updated", -1))
    return render_template_string(INDEX_HTML, movies=movies)

@app.route("/movie/<slug>")
def movie_detail(slug):
    movie = collection.find_one({"slug": slug})
    if not movie:
        logger.warning(f"Movie with slug '{slug}' not found, returning 404.")
        return abort(404)
    return render_template_string(MOVIE_HTML, movie=movie)

@app.route("/watch/<file_id>")
def watch(file_id):
    return redirect(f"https://t.me/{BOT_USERNAME}?start=stream_{file_id}")

@app.route("/download/<file_id>")
def download(file_id):
    return redirect(f"https://t.me/{BOT_USERNAME}?start=download_{file_id}")

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session['logged_in'] = True
            logger.info("Admin logged in successfully.")
            return redirect(url_for("admin"))
        else:
            logger.warning("Failed admin login attempt (wrong password).")
            return render_template_string(LOGIN_HTML, error="Wrong Password")

    if session.get("logged_in"):
        movies = list(collection.find().sort("last_updated", -1))
        return render_template_string(ADMIN_HTML, movies=movies)
    return render_template_string(LOGIN_HTML)

@app.route("/admin/logout")
def logout():
    session.pop("logged_in", None)
    logger.info("Admin logged out.")
    return redirect(url_for("admin"))

@app.route("/admin/delete/<mid>")
def delete(mid):
    if not session.get("logged_in"):
        logger.warning("Unauthorized attempt to delete movie.")
        abort(403)
    try:
        result = collection.delete_one({"_id": ObjectId(mid)})
        if result.deleted_count == 1:
            logger.info(f"Movie with ID {mid} deleted successfully.")
        else:
            logger.warning(f"Attempted to delete movie ID {mid} but it was not found.")
    except Exception as e:
        logger.error(f"Error deleting movie ID {mid}: {e}")
    return redirect(url_for("admin"))

# --- Run Both ---
def run_flask():
    logger.info("Starting Flask app on 0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=True) # debug=True for development

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    bot_thread = threading.Thread(target=bot.run)

    flask_thread.start()
    bot_thread.start()

    logger.info("Both Flask and Pyrogram threads started.")
