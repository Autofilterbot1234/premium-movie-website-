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
CHANNEL_USERNAME = "autoposht"  # আপনার চ্যানেলের সঠিক ইউজারনেম দিন, যেমন @your_channel
BOT_USERNAME = "CtgAutoPostBot"  # <<<<<<< এখানে আপনার বটের সঠিক ইউজারনেম দিন, যেমন @your_bot হলে শুধু "your_bot" লিখুন >>>>>>>
API_ID = 22697010
API_HASH = "fd88d7339b0371eb2a9501d523f3e2a7"
BOT_TOKEN = "7347631253:AAFX3dmD0N8q6u0l2zghoBFu-7TXvMC571M"
ADMIN_PASSWORD = "your_strong_admin_password_here"  # এখানে আপনার শক্তিশালী অ্যাডমিন পাসওয়ার্ড দিন!

# ===== MongoDB Setup =====
mongo = pymongo.MongoClient(MONGO_URI)
db = mongo["movie_db"]
collection = db["movies"]

# ===== Pyrogram Bot Setup =====
bot = Client("movie_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===== Template HTMLs (আগের মতোই আছে) =====
# ... [আপনার HTML টেমপ্লেটগুলি এখানে একই আছে] ...

# ===== Improved Utility Functions =====
def extract_info(text):
    """
    Improved function to extract movie title, year, and quality from various caption formats
    Handles cases like:
    - "Movie Title (2023) 1080p"
    - "Movie Title - 2023 - 720p"
    - "Movie.Title.2023.1080p"
    - "Movie Title [2023] 720p"
    - "Movie Title 2023 480p"
    - "Movie Title 1080p" (without year)
    """
    # Try different patterns sequentially
    patterns = [
        r"^(.*?)\s*(?:\((\d{4})\)|\[(\d{4})\]|\s(\d{4})\s)(?:\s*[-–|]?\s*)?(\d{3,4}p|\d+k)\b",  # Title (Year) Quality
        r"^(.*?)\s*(?:[-–|]\s*)?(\d{3,4}p|\d+k)\b",  # Title - Quality
        r"^(.*?)\s*(\d{4})\s*(?:[-–|]\s*)?(\d{3,4}p|\d+k)\b",  # Title Year Quality
        r"^(.*?)[\.\s](\d{4})[\.\s](\d{3,4}p|\d+k)\b",  # Title.Year.Quality
    ]
    
    title = year = quality = None
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            groups = match.groups()
            title = groups[0].strip()
            
            # Find year in different group positions
            year = next((g for g in groups[1:-1] if g and g.isdigit()), None)
            
            quality = groups[-1].upper()  # Last group is always quality
            if quality.endswith('P') or quality.endswith('K'):
                quality = quality.lower()  # Convert to lowercase (1080p)
            break
    
    # If still no quality found, try to find just quality at the end
    if not quality:
        quality_match = re.search(r"(\d{3,4}p|\d+k)\b", text, re.IGNORECASE)
        if quality_match:
            quality = quality_match.group(1).lower()
            # Extract title as everything before quality
            title = text[:quality_match.start()].strip()
    
    # Clean up title (remove special characters at end)
    if title:
        title = re.sub(r"[\-–|\.\s]+$", "", title).strip()
    
    print(f"Extracted from caption: Title='{title}', Year='{year}', Quality='{quality}'")
    return title, year, quality

def get_tmdb_info(title, year=None):
    """
    Enhanced TMDB lookup with better fallback and year handling
    """
    if not title:
        return {
            "title": "Unknown Title",
            "year": year or "Unknown",
            "poster_url": "",
            "overview": "No information available."
        }
    
    # First try with year if available
    if year and year.isdigit():
        search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}&year={year}"
        res = requests.get(search_url).json()
        
        if res.get("results"):
            return parse_tmdb_result(res["results"][0], title, year)
    
    # Fallback to search without year
    search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}"
    res = requests.get(search_url).json()
    
    if res.get("results"):
        # Find best match by title similarity
        for movie in res["results"]:
            if movie.get("title", "").lower() == title.lower():
                return parse_tmdb_result(movie, title, year)
        
        # Return first result if no exact match
        return parse_tmdb_result(res["results"][0], title, year)
    
    # Final fallback
    return {
        "title": title,
        "year": year or "Unknown",
        "poster_url": "",
        "overview": "No information available from TMDB."
    }

def parse_tmdb_result(movie, original_title, original_year):
    """Helper to parse TMDB result"""
    title = movie.get("title", original_title)
    year = movie.get("release_date", "")[:4] or original_year
    poster_path = movie.get("poster_path", "")
    
    return {
        "title": title,
        "year": year or "Unknown",
        "poster_url": f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else "",
        "overview": movie.get("overview", "No overview available.")
    }

# ===== Improved Pyrogram Bot Handler for Channel Posts =====
@bot.on_message(filters.channel & (filters.video | filters.document))
async def save_movie(client, message):
    print(f"\nNew message in channel {message.chat.title} (ID: {message.chat.id})")
    
    # Get caption or filename
    caption = message.caption or ""
    if not caption and message.document:
        caption = message.document.file_name or ""
    
    print(f"Original caption/filename: {caption}")
    
    # Extract info from caption
    title, year, quality = extract_info(caption)
    
    if not title:
        print("Could not extract title from caption, using default")
        title = "Unknown Title"
    
    if not quality:
        print("Could not extract quality, using default")
        quality = "720p"  # Default quality
    
    # Get file ID based on media type
    if message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
    else:
        print("Unsupported media type, skipping")
        return
    
    print(f"Processing {file_type} - Title: {title}, Year: {year}, Quality: {quality}")
    
    # Get TMDB info
    tmdb_data = get_tmdb_info(title, year)
    actual_title = tmdb_data["title"]
    actual_year = tmdb_data["year"]
    
    # Create slug
    movie_slug = f"{slugify(actual_title)}-{actual_year}"
    if not movie_slug.endswith(actual_year):
        movie_slug += f"-{actual_year}"
    
    print(f"Final movie slug: {movie_slug}")
    
    # Prepare quality entry
    quality_entry = {
        "quality": quality,
        "file_id": file_id,
        "file_type": file_type,
        "added_at": datetime.now()
    }
    
    # Update database
    current_time = datetime.now()
    existing = collection.find_one({"slug": movie_slug})
    
    if existing:
        print(f"Updating existing movie: {actual_title} ({actual_year})")
        
        # Check if this quality already exists
        quality_exists = False
        for q in existing["qualities"]:
            if q["quality"] == quality:
                q.update(quality_entry)
                quality_exists = True
                break
        
        if not quality_exists:
            existing["qualities"].append(quality_entry)
        
        collection.update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "title": actual_title,
                "year": actual_year,
                "overview": tmdb_data["overview"],
                "poster_url": tmdb_data["poster_url"],
                "qualities": existing["qualities"],
                "last_updated": current_time
            }}
        )
    else:
        print(f"Creating new movie: {actual_title} ({actual_year})")
        collection.insert_one({
            "title": actual_title,
            "year": actual_year,
            "overview": tmdb_data["overview"],
            "poster_url": tmdb_data["poster_url"],
            "qualities": [quality_entry],
            "slug": movie_slug,
            "created_at": current_time,
            "last_updated": current_time,
            "source": "telegram_channel"
        })
    
    print(f"Successfully processed {actual_title} ({actual_year}) [{quality}]\n")

# ... [আপনার বাকি কোড যেমন /start হ্যান্ডলার এবং ফ্লাস্ক রাউটস একই আছে] ...

# ===== RUN BOTH =====
def run_flask_app():
    print("Starting Flask app...")
    app.run(host="0.0.0.0", port=5000, debug=False)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.start()
    
    print("Starting Telegram Bot...")
    bot.run()
