import os
import threading
import requests
import logging
import re
from flask import Flask, render_template_string, abort # Added abort for 404
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from bson.objectid import ObjectId # To handle MongoDB's ObjectId

# ==================== Configuration Loading and Validation ====================
REQUIRED_ENV_VARS = [
    "API_ID",
    "API_HASH",
    "BOT_TOKEN",
    "CHANNEL",
    "MONGO_URI",
    "OMDB_API_KEY",
    "BOT_USERNAME", # Your bot's username (e.g., MyMovieBot)
    "WEBSITE_URL"   # Your website's public URL (e.g., https://yourwebsite.render.com)
]

env_vars = {}
for var in REQUIRED_ENV_VARS:
    value = os.environ.get(var)
    if not value:
        logging.error(f"Error: Environment variable '{var}' is not set. Please set it before running the script.")
        exit(1)
    env_vars[var] = value

try:
    API_ID = int(env_vars["API_ID"])
except ValueError:
    logging.error("Error: API_ID must be an integer.")
    exit(1)

API_HASH = env_vars["API_HASH"]
BOT_TOKEN = env_vars["BOT_TOKEN"]
CHANNEL = env_vars["CHANNEL"]
MONGO_URI = env_vars["MONGO_URI"]
OMDB_API_KEY = env_vars["OMDB_API_KEY"]
BOT_USERNAME = env_vars["BOT_USERNAME"].lstrip('@')
WEBSITE_URL = env_vars["WEBSITE_URL"].rstrip('/') # Remove trailing slash

try:
    DELETE_AFTER = int(os.environ.get("DELETE_AFTER", 300))
except ValueError:
    logging.warning("Warning: DELETE_AFTER is not a valid integer. Using default value 300 seconds.")
    DELETE_AFTER = 300

# ==================== Logging Setup ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== Database Setup ====================
try:
    mongo = MongoClient(MONGO_URI)
    db = mongo["movie_db"]
    col = db["movies"]
    mongo.admin.command('ping')
    logger.info("MongoDB connected successfully.")
except PyMongoError as e:
    logger.error(f"MongoDB connection or operation error: {e}. Please check MONGO_URI and MongoDB server status.")
    exit(1)

# ==================== Flask Site ====================
app = Flask(__name__)

# --- Home Page ---
@app.route("/")
def home():
    """Renders the home page with a grid of movie posters."""
    try:
        data = list(col.find().sort("_id", -1))

        html = """
        <html>
        <head>
            <title>🎬 Movie Zone - Latest Movies</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #1a1a2e; color: #e0e0e0; padding: 20px; margin: 0; }
            .container { max-width: 960px; margin: 20px auto; background: #2a2a4a; padding: 25px; border-radius: 10px; box-shadow: 0 5px 15px rgba(0, 0, 0, 0.5); }
            h1 { color: #00f7ff; text-align: center; margin-bottom: 30px; font-size: 2.5em; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); }
            .movie-grid {
                display: grid;
                grid-template-columns: 1fr 1fr; /* Two columns */
                gap: 25px;
                padding: 10px;
            }
            .movie-item {
                background: #3a3a5a;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 3px 8px rgba(0, 0, 0, 0.3);
                transition: transform 0.3s ease-in-out;
                text-align: center;
            }
            .movie-item:hover {
                transform: translateY(-5px);
            }
            .movie-item a {
                text-decoration: none;
                color: inherit;
            }
            .movie-item img {
                width: 100%;
                height: 300px; /* Fixed height for posters */
                object-fit: cover; /* Cover the area, cropping if necessary */
                border-bottom: 2px solid #5a5a7a;
                transition: border-color 0.3s ease;
            }
            .movie-item img:hover {
                border-color: #00f7ff;
            }
            .movie-item h3 {
                color: #88c0d0;
                margin: 15px 10px;
                font-size: 1.3em;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            @media (max-width: 600px) {
                .movie-grid {
                    grid-template-columns: 1fr; /* One column on small screens */
                }
            }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🍿 Latest Movies</h1>
                {% if movies %}
                <div class="movie-grid">
                    {% for m in movies %}
                    <div class="movie-item">
                        <a href="/movie/{{ m._id }}">
                            <img src="{{ m.poster }}" alt="{{ m.title }} Poster"/>
                            <h3>{{ m.title }} ({{ m.year }})</h3>
                        </a>
                    </div>
                    {% endfor %}
                </div>
                {% else %}
                <p style="text-align: center; color: #c0c0d0;">No movies found yet. Share some movies in your Telegram channel!</p>
                {% endif %}
            </div>
        </body>
        </html>
        """
        return render_template_string(html, movies=data)
    except Exception as e:
        logger.error(f"Error rendering Flask home page: {e}")
        return "An internal server error occurred.", 500

# --- Movie Detail Page ---
@app.route("/movie/<movie_id>")
def movie_detail(movie_id):
    """Renders the detailed page for a single movie."""
    try:
        # Fetch movie from MongoDB using its _id
        # Ensure movie_id is a valid ObjectId
        try:
            movie_obj_id = ObjectId(movie_id)
        except:
            abort(404) # Invalid movie ID format

        movie = col.find_one({"_id": movie_obj_id})

        if not movie:
            abort(404) # Movie not found in DB

        html = f"""
        <html>
        <head>
            <title>🎬 {{{{ movie.title }}}} ({{{{ movie.year }}}})</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #1a1a2e; color: #e0e0e0; padding: 20px; margin: 0; line-height: 1.6; }}
            .container {{ max-width: 800px; margin: 20px auto; background: #2a2a4a; padding: 25px; border-radius: 10px; box-shadow: 0 5px 15px rgba(0, 0, 0, 0.5); display: flex; flex-wrap: wrap; }}
            .poster-area {{ flex: 1; min-width: 250px; margin-right: 25px; text-align: center; }}
            .poster-area img {{ width: 100%; max-width: 300px; height: auto; border-radius: 8px; border: 3px solid #00f7ff; box-shadow: 0 4px 10px rgba(0, 0, 0, 0.4); }}
            .details-area {{ flex: 2; min-width: 300px; }}
            h1 {{ color: #00f7ff; margin-top: 0; margin-bottom: 10px; font-size: 2.2em; }}
            p {{ margin-bottom: 8px; color: #c0c0d0; }}
            strong {{ color: #aaffee; }}
            .movie-buttons {{ margin-top: 20px; display: flex; flex-wrap: wrap; gap: 15px; }}
            .movie-buttons a {{
                display: inline-flex;
                align-items: center;
                background-color: #007bff;
                color: white;
                padding: 12px 25px;
                border-radius: 8px;
                text-decoration: none;
                font-weight: bold;
                font-size: 1.1em;
                transition: background-color 0.3s ease, transform 0.2s ease;
                box-shadow: 0 3px 8px rgba(0, 0, 0, 0.3);
            }}
            .movie-buttons a:hover {{
                background-color: #0056b3;
                transform: translateY(-2px);
            }}
            .movie-buttons a svg {{ margin-right: 8px; }}
            .back-button {{
                display: block;
                margin-top: 30px;
                text-align: center;
            }}
            .back-button a {{
                color: #88c0d0;
                text-decoration: none;
                font-weight: bold;
                transition: color 0.2s ease;
            }}
            .back-button a:hover {{
                color: #00f7ff;
                text-decoration: underline;
            }}

            @media (max-width: 768px) {{
                .container {{
                    flex-direction: column;
                    align-items: center;
                    text-align: center;
                }}
                .poster-area {{
                    margin-right: 0;
                    margin-bottom: 25px;
                }}
                .details-area {{
                    min-width: unset;
                }}
                .movie-buttons {{
                    justify-content: center;
                }}
            }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="poster-area">
                    {{% if movie.poster %}}
                    <img src="{{{{ movie.poster }}}}" alt="{{{{ movie.title }}}} Poster"/>
                    {{% else %}}
                    <img src="https://via.placeholder.com/300x450?text=No+Poster" alt="No Poster Available"/>
                    {{% endif %}}
                </div>
                <div class="details-area">
                    <h1>{{{{ movie.title }}}} ({{{{ movie.year }}}})</h1>
                    <p><strong>Language:</strong> {{{{ movie.language }}}} | ⭐ <strong>IMDb:</strong> {{{{ movie.rating }}}}</p>
                    <p><strong>Plot:</strong> {{{{ movie.plot }}}}</p>
                    <div class="movie-buttons">
                        {{% if movie.file_id %}}
                            <a href="https://t.me/{BOT_USERNAME}?start=get_file_{{{{ movie.file_id }}}}" target="_blank" rel="noopener noreferrer">
                                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="feather feather-download"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                                Download via Bot
                            </a>
                        {{% endif %}}
                        {{% if movie.external_watch_link %}}
                            <a href="{{{{ movie.external_watch_link }}}}" target="_blank" rel="noopener noreferrer">
                                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="feather feather-play-circle"><circle cx="12" cy="12" r="10"></circle><polygon points="10 8 16 12 10 16 10 8"></polygon></svg>
                                Watch Online
                            </a>
                        {{% endif %}}
                        {{% if not movie.file_id and not movie.external_watch_link %}}
                            <a href="{{{{ movie.telegram_link }}}}" target="_blank" rel="noopener noreferrer">
                                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="feather feather-send"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                                View Telegram Post
                            </a>
                        {{% endif %}}
                    </div>
                </div>
            </div>
            <div class="back-button">
                <a href="/">← Back to Movies</a>
            </div>
        </body>
        </html>
        """
        return render_template_string(html, movie=movie, BOT_USERNAME=BOT_USERNAME)
    except Exception as e:
        logger.error(f"Error rendering movie detail page for ID {movie_id}: {e}")
        return "An internal server error occurred.", 500

# ==================== Telegram Bot ====================
bot = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@bot.on_message(filters.command("start"))
async def start_command(client, message):
    # Check for deep linking payload (e.g., /start get_file_FILE_ID)
    if message.text and " " in message.text:
        payload = message.text.split(" ", 1)[1]
        if payload.startswith("get_file_"):
            requested_file_id = payload.replace("get_file_", "")
            logger.info(f"User {message.from_user.id} requested file: {requested_file_id}")
            try:
                # Send the document (movie) to the user
                await client.send_document(
                    chat_id=message.chat.id,
                    document=requested_file_id,
                    caption=f"Here's your requested movie from Movie Zone! Enjoy.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Go to Website", url=WEBSITE_URL)]])
                )
                logger.info(f"Sent file {requested_file_id} to user {message.from_user.id}")
            except Exception as e:
                logger.error(f"Error sending file {requested_file_id} to user {message.from_user.id}: {e}")
                await message.reply_text("Sorry, I could not send the file. It might be too large or an error occurred. Please try again later.")
            return

    # Default /start message if no deep link payload
    await message.reply_text(
        "Hi! Welcome to the Movie Zone bot. Click 'Go to Website' to browse latest movies.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Go to Website", url=WEBSITE_URL)]
        ])
    )

@bot.on_message(filters.chat(CHANNEL) & filters.media)
async def save_movie(client, message):
    caption = message.caption or ""
    raw_title_line = caption.split("\n")[0].strip()

    if not raw_title_line:
        logger.info(f"Skipping message {message.id} in {CHANNEL}: No title found in caption.")
        return

    # Extract Telegram file_id
    file_id = None
    if message.video:
        file_id = message.video.file_id
    elif message.document:
        file_id = message.document.file_id
    elif message.audio:
        file_id = message.audio.file_id
    
    if not file_id:
        logger.warning(f"No usable file_id found for message {message.id}. Skipping file save for direct bot download.")
        # Proceed with OMDb fetching even without file_id, but the download link won't work
        # You might consider raising an error or returning here if file_id is mandatory.
        pass

    # ============ START: Title Cleaning Logic ============
    title_to_search = raw_title_line

    year = None
    year_match = re.search(r'\(?(\d{4})\)?', title_to_search)
    if year_match:
        year = year_match.group(1)
        title_to_search = re.sub(r'[\(\[\.]?' + re.escape(year_match.group(0)) + r'[\)\]\.]?', ' ', title_to_search).strip()

    patterns_to_remove = [
        r'\b\d{3,4}p\b', r'\b(?:WEB-DL|HDRip|BluRay|DVDRip|BRRip|WEBRip|HDTV|BDRip|Rip)\b',
        r'\b(?:HEVC|x264|x265|AAC|AC3|DD5\.1|DTS|XviD|MP4|MKV|AVI|FLAC|H\.264|H\.265)\b',
        r'\b(?:HQ Line Audio|Line Audio|Dubbed|ESubs|Subbed|TG|www\.[a-z0-9\-\.]+\.(?:com|net|org))\b',
        r'\b(?:Hindi|Bengali|English|Multi|Dual Audio|Org Audio)\b', r'\[.*?\]',
        r'\(.*?\)', r'-\s*\d+', r'\s*[\._-]\s*', r'trailer', r'full movie', r'sample',
        r'\b(?:x264|x265)\b-\w+', r'repack', r'proper', r'uncut', r'extended', r'director\'s cut',
        r'\b(?:truehd|dts-hd|ac3|eac3|doby)\b', r'\b(?:imax|hdr|uhd|4k|fhd|hd)\b',
        r'\bleaked\b',
        r'[\u0980-\u09FF]+' # Remove Bengali characters
    ]

    for pattern in patterns_to_remove:
        title_to_search = re.sub(pattern, ' ', title_to_search, flags=re.IGNORECASE).strip()

    title_to_search = re.sub(r'\s{2,}', ' ', title_to_search).strip()

    if len(title_to_search) < 3 or re.match(r'^\W*$', title_to_search):
        logger.warning(f"Cleaned title '{title_to_search}' is too short/invalid for '{raw_title_line}'. Trying simpler parse.")
        fallback_match = re.match(r'([^.\[\(]+)', raw_title_line)
        if fallback_match:
            title_to_search = fallback_match.group(1).strip()
        else:
            title_to_search = raw_title_line.split("(")[0].strip()

    if not title_to_search or len(title_to_search) < 3:
        title_to_search = raw_title_line
        logger.warning(f"Could not effectively clean title for OMDb. Using original first line: '{title_to_search}'")
    # ============ END: Title Cleaning Logic ============

    omdb_url = f"http://www.omdbapi.com/?t={title_to_search}&apikey={OMDB_API_KEY}"
    if year:
        omdb_url += f"&y={year}"

    logger.info(f"🎬 Attempting to process: '{raw_title_line}' (Cleaned for OMDb: '{title_to_search}' | Year: {year or 'N/A'})")

    try:
        r = requests.get(omdb_url, timeout=10)
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching from OMDb for '{title_to_search}': {e}")
        return

    if data.get("Response") != "True":
        logger.warning(f"❌ Movie '{title_to_search}' (from '{raw_title_line}') not found in OMDb or API error: {data.get('Error', 'Unknown Error')}")
        return

    movie_data = {
        "title": data.get("Title"),
        "year": data.get("Year"),
        "language": data.get("Language"),
        "rating": data.get("imdbRating"),
        "poster": data.get("Poster"),
        "plot": data.get("Plot"),
        "telegram_link": f"https://t.me/{CHANNEL.strip('@')}/{message.id}",
        "file_id": file_id, # Save the Telegram file_id
        "external_watch_link": None # Add this if you want to manually include an external watch link in the caption sometimes
    }

    try:
        # Check if movie already exists to avoid duplicates based on title and year
        # For updates, we can update if a movie with same title/year already exists and new file_id or external_watch_link is provided
        existing_movie = col.find_one({"title": movie_data["title"], "year": movie_data["year"]})
        if existing_movie:
            # If movie exists, update its file_id if a new one is found (e.g., if you re-upload)
            # You might want more sophisticated update logic here
            col.update_one(
                {"_id": existing_movie["_id"]},
                {"$set": {"file_id": file_id, "telegram_link": movie_data["telegram_link"]}} # Update file_id and telegram link
            )
            logger.info(f"⚠️ Movie '{movie_data['title']} ({movie_data['year']})' already exists. Updated file_id and telegram_link.")
        else:
            col.insert_one(movie_data)
            logger.info(f"✅ Saved movie to DB: {movie_data['title']} ({movie_data['year']}) with file_id: {file_id}")
    except PyMongoError as e:
        logger.error(f"Database error when saving movie '{movie_data['title']}': {e}")

    if DELETE_AFTER > 0:
        try:
            await message.delete(delay=DELETE_AFTER)
            logger.info(f"Scheduled deletion of message {message.id} in {DELETE_AFTER} seconds.")
        except Exception as e:
            logger.warning(f"Could not schedule deletion for message {message.id}: {e}")

# ==================== Run Bot + Web ====================
if __name__ == "__main__":
    flask_thread = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=8080, debug=False))
    flask_thread.daemon = True
    flask_thread.start()
    logger.info("Flask web server started on http://0.0.0.0:8080")

    logger.info("Starting Telegram bot...")
    bot.run()
    logger.info("Telegram bot stopped.")
