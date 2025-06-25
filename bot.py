import os
import threading
import requests
import logging
import re # Added for regular expressions
from flask import Flask, render_template_string
from pyrogram import Client, filters
from pymongo import MongoClient
from pymongo.errors import PyMongoError

# ==================== Configuration Loading and Validation ====================
# Define required environment variables
REQUIRED_ENV_VARS = [
    "API_ID",
    "API_HASH",
    "BOT_TOKEN",
    "CHANNEL",
    "MONGO_URI",
    "OMDB_API_KEY"
]

# Load and validate all environment variables
env_vars = {}
for var in REQUIRED_ENV_VARS:
    value = os.environ.get(var)
    if not value:
        logging.error(f"Error: Environment variable '{var}' is not set. Please set it before running the script.")
        exit(1) # Exit if any required variable is missing
    env_vars[var] = value

# Special handling for integer environment variables
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

# Optional variable with a default value
try:
    DELETE_AFTER = int(os.environ.get("DELETE_AFTER", 300)) # Default 5 minutes (300 seconds)
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
    # Test connection
    mongo.admin.command('ping') # A simple command to verify connection
    logger.info("MongoDB connected successfully.")
except PyMongoError as e: # Catch all PyMongo-related errors, including connection issues
    logger.error(f"MongoDB connection or operation error: {e}. Please check MONGO_URI and MongoDB server status.")
    exit(1)

# ==================== Flask Site ====================
app = Flask(__name__)

@app.route("/")
def home():
    """Renders the home page with a list of movies from the database."""
    try:
        data = list(col.find().sort("_id", -1))
        # Enhanced HTML/CSS for a better look and feel
        html = """
        <html>
        <head>
            <title>🎬 Movie Zone</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #1a1a2e; color: #e0e0e0; padding: 20px; line-height: 1.6; margin: 0; }
            .container { max-width: 900px; margin: 20px auto; background: #2a2a4a; padding: 25px; border-radius: 10px; box-shadow: 0 5px 15px rgba(0, 0, 0, 0.5); }
            h1 { color: #00f7ff; text-align: center; margin-bottom: 30px; font-size: 2.5em; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); }
            .movie { background: #3a3a5a; padding: 18px; border-radius: 8px; margin-bottom: 25px; display: flex; align-items: flex-start; box-shadow: 0 3px 8px rgba(0, 0, 0, 0.3); transition: transform 0.3s ease-in-out; }
            .movie:hover { transform: translateY(-5px); }
            .movie img { width: 160px; height: auto; flex-shrink: 0; margin-right: 25px; border-radius: 5px; border: 2px solid #5a5a7a; transition: border-color 0.3s ease; }
            .movie img:hover { border-color: #00f7ff; }
            .movie-details { flex-grow: 1; }
            h2 { color: #88c0d0; margin-top: 0; margin-bottom: 10px; font-size: 1.9em; }
            p { margin-bottom: 7px; color: #c0c0d0; }
            a { color: #00f7ff; text-decoration: none; transition: color 0.2s ease-in-out; }
            a:hover { color: #4ddbff; text-decoration: underline; }
            strong { color: #aaffee; }
            .clear-float { clear: both; }

            /* Responsive adjustments */
            @media (max-width: 768px) {
                .movie {
                    flex-direction: column;
                    align-items: center;
                    text-align: center;
                }
                .movie img {
                    margin-right: 0;
                    margin-bottom: 15px;
                }
            }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🍿 Latest Movies</h1>
                {% for m in movies %}
                <div class="movie">
                    <a href="{{m.link}}" target="_blank" rel="noopener noreferrer">
                        <img src="{{m.poster}}" alt="{{m.title}} Poster"/>
                    </a>
                    <div class="movie-details">
                        <h2>{{m.title}} ({{m.year}})</h2>
                        <p><strong>Language:</strong> {{m.language}} | ⭐ <strong>IMDb:</strong> {{m.rating}}</p>
                        <p>{{m.plot}}</p>
                        <p><a href="{{m.link}}" target="_blank" rel="noopener noreferrer">📥 Download / 🎬 Watch</a></p>
                    </div>
                    <div class="clear-float"></div>
                </div>
                {% else %}
                <p style="text-align: center; color: #c0c0d0;">No movies found yet. Share some movies in your Telegram channel!</p>
                {% endfor %}
            </div>
        </body>
        </html>
        """
        return render_template_string(html, movies=data)
    except Exception as e:
        logger.error(f"Error rendering Flask home page: {e}")
        return "An internal server error occurred.", 500

# ==================== Telegram Bot ====================
bot = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@bot.on_message(filters.chat(CHANNEL) & filters.media)
async def save_movie(client, message):
    """
    Handles new media messages in the specified Telegram channel.
    Extracts movie title, fetches details from OMDb API,
    and saves the movie information to MongoDB.
    """
    caption = message.caption or ""
    raw_title = caption.split("\n")[0].strip()

    if not raw_title:
        logger.info(f"Skipping message {message.id} in {CHANNEL}: No title found in caption.")
        return

    # ============ START: Title Cleaning Logic ============
    title_to_search = raw_title

    # Extract year if present (e.g., Movie Title (2022) or Movie.Title.2022)
    year = None
    year_match = re.search(r'\(?(\d{4})\)?', title_to_search)
    if year_match:
        year = year_match.group(1)
        # Remove the year and its surrounding brackets/dots from the title
        title_to_search = re.sub(r'[\(\[\.]?' + re.escape(year_match.group(0)) + r'[\)\]\.]?', ' ', title_to_search).strip()

    # Define patterns to remove common file name noise
    patterns_to_remove = [
        r'\b\d{3,4}p\b',                                     # 720p, 1080p, 480p (resolution)
        r'\b(?:WEB-DL|HDRip|BluRay|DVDRip|BRRip|WEBRip|HDTV|BDRip|Rip)\b', # source quality
        r'\b(?:HEVC|x264|x265|AAC|AC3|DD5\.1|DTS|XviD|MP4|MKV|AVI|FLAC|H\.264|H\.265)\b', # codec/audio/container
        r'\b(?:HQ Line Audio|Line Audio|Dubbed|ESubs|Subbed|TG|www\.[a-z0-9\-\.]+\.(?:com|net|org))\b', # other irrelevant words/watermarks
        r'\b(?:Hindi|Bengali|English|Multi|Dual Audio|Org Audio)\b', # language
        r'\[.*?\]',                                         # [কিছু টেক্সট] যেমন [www.example.com]
        r'\(.*?\)',                                         # (কিছু টেক্সট) যদি এটি বছর না হয় এবং ব্র্যাকেটে থাকে
        r'-\s*\d+',                                         # - 1, - 2 (যেমন পার্ট নম্বর)
        r'\s*[\._-]\s*',                                    # Dot, underscore, dash that are not word separators
        r'trailer', r'full movie', r'sample',               # common extra words
        r'\b(?:x264|x265)\b-\w+',                            # example: x264-EVO, x265-RARBG
        r'repack', r'proper', r'uncut', r'extended', r'director\'s cut', # version indicators
        r'\b(?:truehd|dts-hd|ac3|eac3|doby)\b',              # more audio formats
        r'\b(?:imax|hdr|uhd|4k|fhd|hd)\b',                   # more quality indicators
    ]

    for pattern in patterns_to_remove:
        title_to_search = re.sub(pattern, ' ', title_to_search, flags=re.IGNORECASE).strip()

    # Clean up multiple spaces and trim whitespace
    title_to_search = re.sub(r'\s{2,}', ' ', title_to_search).strip()

    # Final check: if cleaning made the title too short or empty, try a simpler approach
    # e.g., take text before first common separator or bracket if the cleaned title is bad
    if len(title_to_search) < 3 or re.match(r'^\W*$', title_to_search): # If title is too short or only non-word chars
        logger.warning(f"Cleaned title '{title_to_search}' is too short/invalid for '{raw_title}'. Trying simpler parse.")
        # Attempt to get text before first common separator or bracket for a fallback title
        fallback_match = re.match(r'([^.\[\(]+)', raw_title)
        if fallback_match:
            title_to_search = fallback_match.group(1).strip()
        else:
            title_to_search = raw_title.split("(")[0].strip() # Last resort, text before first '('

    # If after all attempts, title is still empty or too generic, use original but log warning
    if not title_to_search or len(title_to_search) < 3:
        title_to_search = raw_title.split("\n")[0].strip() # Use original first line as last resort
        logger.warning(f"Could not effectively clean title for OMDb. Using original first line: '{title_to_search}'")

    # ============ END: Title Cleaning Logic ============

    # OMDB Fetch using the cleaned title and extracted year
    omdb_url = f"http://www.omdbapi.com/?t={title_to_search}&apikey={OMDB_API_KEY}"
    if year:
        omdb_url += f"&y={year}" # Add year parameter if available

    logger.info(f"🎬 Attempting to process: '{raw_title}' (Cleaned for OMDb: '{title_to_search}' | Year: {year or 'N/A'})")

    # Fetch movie details from OMDb
    try:
        r = requests.get(omdb_url, timeout=10) # Added timeout for robustness
        r.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        data = r.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching from OMDb for '{title_to_search}': {e}")
        return

    if data.get("Response") != "True":
        logger.warning(f"❌ Movie '{title_to_search}' (from '{raw_title}') not found in OMDb or API error: {data.get('Error', 'Unknown Error')}")
        return

    movie_data = {
        "title": data.get("Title"),
        "year": data.get("Year"),
        "language": data.get("Language"),
        "rating": data.get("imdbRating"),
        "poster": data.get("Poster"),
        "plot": data.get("Plot"),
        "link": f"https://t.me/{CHANNEL.strip('@')}/{message.id}"
    }

    try:
        # Check if movie already exists to avoid duplicates based on title and year
        if not col.find_one({"title": movie_data["title"], "year": movie_data["year"]}):
            col.insert_one(movie_data)
            logger.info(f"✅ Saved movie to DB: {movie_data['title']} ({movie_data['year']})")
        else:
            logger.info(f"⚠️ Movie '{movie_data['title']} ({movie_data['year']})' already exists in DB. Skipping.")
    except PyMongoError as e:
        logger.error(f"Database error when saving movie '{movie_data['title']}': {e}")

    # Schedule message deletion from Telegram channel after DELETE_AFTER seconds
    if DELETE_AFTER > 0:
        try:
            await message.delete(delay=DELETE_AFTER)
            logger.info(f"Scheduled deletion of message {message.id} in {DELETE_AFTER} seconds.")
        except Exception as e:
            logger.warning(f"Could not schedule deletion for message {message.id}: {e}")

# ==================== Run Bot + Web ====================
if __name__ == "__main__":
    # Start Flask web server in a separate thread
    flask_thread = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=8080, debug=False))
    flask_thread.daemon = True # Allow Flask thread to exit when main program exits
    flask_thread.start()
    logger.info("Flask web server started on http://0.0.0.0:8080")

    # Start Pyrogram bot (blocking call)
    logger.info("Starting Telegram bot...")
    bot.run()
    logger.info("Telegram bot stopped.")
