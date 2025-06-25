import os
import threading
import requests
import logging
from flask import Flask, render_template_string
from pyrogram import Client, filters
from pymongo import MongoClient
from pymongo.errors import ConnectionError, PyMongoError

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
    mongo.admin.command('ping')
    logger.info("MongoDB connected successfully.")
except ConnectionError as e:
    logger.error(f"Could not connect to MongoDB: {e}. Please check MONGO_URI.")
    exit(1) # Exit if database connection fails
except PyMongoError as e:
    logger.error(f"MongoDB error: {e}. Please check MongoDB server status or MONGO_URI.")
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
    title_line = caption.split("\n")[0].strip()

    if not title_line:
        logger.info(f"Skipping message {message.id} in {CHANNEL}: No title found in caption.")
        return

    logger.info(f"🎬 Processing message {message.id} for movie: {title_line}")

    # Fetch movie details from OMDb
    omdb_url = f"http://www.omdbapi.com/?t={title_line}&apikey={OMDB_API_KEY}"
    try:
        r = requests.get(omdb_url, timeout=10) # Added timeout for robustness
        r.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        data = r.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching from OMDb for '{title_line}': {e}")
        return

    if data.get("Response") != "True":
        logger.warning(f"❌ Movie '{title_line}' not found in OMDb or API error: {data.get('Error', 'Unknown Error')}")
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

