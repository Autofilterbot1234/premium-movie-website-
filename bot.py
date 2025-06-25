import os
import threading
import requests
import logging
import re
from flask import Flask, render_template_string, abort, request, redirect, url_for, session, flash # Added session, flash
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from bson.objectid import ObjectId
from functools import wraps # For login_required decorator

# ==================== Configuration Loading and Validation ====================
REQUIRED_ENV_VARS = [
    "API_ID",
    "API_HASH",
    "BOT_TOKEN",
    "CHANNEL",
    "MONGO_URI",
    "OMDB_API_KEY",
    "BOT_USERNAME", # Your bot's username (e.g., MyMovieBot)
    "WEBSITE_URL",  # Your website's public URL (e.g., https://yourwebsite.render.com)
    "SECRET_KEY",   # For Flask session management
    "ADMIN_USERNAME", # Admin panel username
    "ADMIN_PASSWORD"  # Admin panel password
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
SECRET_KEY = env_vars["SECRET_KEY"]
ADMIN_USERNAME = env_vars["ADMIN_USERNAME"]
ADMIN_PASSWORD = env_vars["ADMIN_PASSWORD"]

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
app.secret_key = SECRET_KEY # Set secret key for session management

# Decorator to check if admin is logged in
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# HTML Snippets for reusability and cleaner code
HEADER_HTML = """
    <header class="main-header">
        <div class="header-inner">
            <a href="/" class="logo">🎬 Movie Zone</a>
            <div class="search-bar">
                <form action="/search" method="get">
                    <input type="text" name="q" placeholder="Search movies..." value="{{ request.args.get('q', '') }}">
                    <button type="submit">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                    </button>
                </form>
            </div>
            <div class="menu-icon">
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>
            </div>
        </div>
    </header>
"""

BASE_CSS = """
    <style>
    :root {
        --bg-dark: #121212;
        --bg-medium: #1f1f1f;
        --bg-light: #2c2c2c;
        --text-color: #e0e0e0;
        --primary-color: #00f7ff; /* A vibrant teal/cyan */
        --accent-color: #ffc107; /* Yellow for ratings */
        --button-bg: #007bff; /* Blue for primary actions */
        --button-hover: #0056b3;
        --border-color: #333;
        --card-shadow: rgba(0, 0, 0, 0.4);
        --danger-color: #dc3545;
        --success-color: #28a745;
    }

    * {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
    }

    body {
        font-family: 'Inter', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        background: var(--bg-dark);
        color: var(--text-color);
        line-height: 1.6;
        padding-bottom: 50px; /* Space for potential footer/nav */
    }

    a {
        color: var(--primary-color);
        text-decoration: none;
    }
    a:hover {
        text-decoration: underline;
    }

    .container {
        max-width: 1200px;
        margin: 0 auto;
        padding: 20px;
    }

    /* Header */
    .main-header {
        background: var(--bg-medium);
        padding: 15px 20px;
        box-shadow: 0 2px 10px var(--card-shadow);
        position: sticky;
        top: 0;
        z-index: 1000;
    }

    .header-inner {
        max-width: 1200px;
        margin: 0 auto;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 20px;
    }

    .logo {
        color: var(--primary-color);
        font-size: 1.8em;
        font-weight: bold;
        text-decoration: none;
        flex-shrink: 0;
    }

    .search-bar {
        flex-grow: 1;
        display: flex;
        justify-content: center; /* Center search bar in available space */
    }

    .search-bar form {
        display: flex;
        width: 100%;
        max-width: 500px; /* Max width for search input */
        background: var(--bg-light);
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid var(--border-color);
    }

    .search-bar input[type="text"] {
        flex-grow: 1;
        padding: 10px 15px;
        border: none;
        background: transparent;
        color: var(--text-color);
        font-size: 1em;
        outline: none;
    }

    .search-bar input[type="text"]::placeholder {
        color: #888;
    }

    .search-bar button {
        background: var(--primary-color);
        border: none;
        padding: 10px 15px;
        cursor: pointer;
        transition: background-color 0.2s ease;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .search-bar button:hover {
        background-color: #00b0ff;
    }

    .search-bar button svg {
        color: var(--bg-dark); /* Dark icon on bright button */
    }

    .menu-icon {
        color: var(--text-color);
        cursor: pointer;
        display: none; /* Hidden on larger screens */
    }

    /* Sections */
    .section-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 40px;
        margin-bottom: 25px;
        border-left: 5px solid var(--primary-color);
        padding-left: 15px;
    }

    .section-header h2 {
        color: var(--text-color);
        font-size: 1.8em;
    }

    .section-controls {
        display: flex;
        align-items: center;
        gap: 15px;
    }

    .section-controls a {
        color: var(--primary-color);
        text-decoration: none;
        font-weight: bold;
        transition: color 0.2s ease;
    }

    .section-controls a:hover {
        color: #00b0ff;
    }

    .nav-arrows svg {
        color: var(--text-color);
        cursor: pointer;
        opacity: 0.7;
        transition: opacity 0.2s ease;
    }

    .nav-arrows svg:hover {
        opacity: 1;
    }

    /* Featured Movie */
    .featured-movie {
        position: relative;
        height: 400px;
        background-color: var(--bg-medium);
        border-radius: 10px;
        overflow: hidden;
        margin-top: 30px;
        display: flex;
        align-items: flex-end;
        padding: 30px;
        background-size: cover;
        background-position: center;
        box-shadow: 0 5px 15px var(--card-shadow);
    }

    .featured-movie::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(to top, rgba(18, 18, 18, 0.9) 0%, rgba(18, 18, 18, 0) 70%);
        z-index: 1;
    }

    .featured-content {
        position: relative;
        z-index: 2;
        max-width: 600px;
        color: white;
    }

    .featured-content h2 {
        font-size: 2.5em;
        margin-bottom: 10px;
        color: var(--primary-color);
        text-shadow: 2px 2px 5px rgba(0,0,0,0.7);
    }

    .featured-content p {
        font-size: 1.1em;
        margin-bottom: 20px;
        color: #c0c0c0;
    }

    .featured-actions {
        display: flex;
        gap: 15px;
        align-items: center;
    }

    .featured-actions .watch-btn {
        background: var(--primary-color);
        color: var(--bg-dark);
        padding: 12px 25px;
        border-radius: 30px;
        text-decoration: none;
        font-weight: bold;
        display: flex;
        align-items: center;
        gap: 8px;
        transition: background-color 0.2s ease;
    }

    .featured-actions .watch-btn:hover {
        background-color: #00b0ff;
    }

    .featured-actions .rating {
        background: var(--bg-light);
        color: var(--accent-color);
        padding: 8px 15px;
        border-radius: 20px;
        font-weight: bold;
        display: flex;
        align-items: center;
        gap: 5px;
    }

    .featured-actions .rating svg {
        color: var(--accent-color);
    }

    /* Movie Grid */
    .movie-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
        gap: 25px;
        padding: 10px;
    }

    .movie-item {
        background: var(--bg-medium);
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 3px 8px var(--card-shadow);
        transition: transform 0.2s ease-in-out, box-shadow 0.2s ease;
        position: relative;
    }

    .movie-item:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 20px var(--card-shadow);
    }

    .movie-item a {
        text-decoration: none;
        color: inherit;
        display: block;
    }

    .movie-item img {
        width: 100%;
        height: 270px; /* Fixed height for posters */
        object-fit: cover;
        display: block;
        border-bottom: 1px solid var(--border-color);
    }

    .movie-item-content {
        padding: 12px;
        position: relative; /* For tags */
    }

    .movie-item h3 {
        color: var(--text-color);
        font-size: 1.1em;
        margin-bottom: 5px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .movie-item p {
        color: #aaa;
        font-size: 0.9em;
    }

    .movie-item .rating-badge {
        position: absolute;
        top: 8px;
        left: 8px;
        background: rgba(0, 0, 0, 0.7);
        color: var(--accent-color);
        padding: 4px 8px;
        border-radius: 5px;
        font-size: 0.8em;
        font-weight: bold;
        display: flex;
        align-items: center;
        gap: 3px;
    }

    .movie-item .rating-badge svg {
        width: 12px;
        height: 12px;
        color: var(--accent-color);
    }

    .movie-tags {
        position: absolute;
        bottom: 10px;
        left: 10px;
        right: 10px;
        display: flex;
        flex-wrap: wrap;
        gap: 5px;
        z-index: 5;
    }

    .movie-tag {
        background: rgba(0, 0, 0, 0.6);
        color: white;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 0.75em;
        white-space: nowrap;
    }
    
    /* Movie Detail Page */
    .detail-container {
        display: flex;
        flex-direction: column;
        gap: 30px;
        padding: 30px 20px;
        background: var(--bg-medium);
        border-radius: 10px;
        box-shadow: 0 5px 20px var(--card-shadow);
        max-width: 900px;
        margin: 30px auto;
    }

    .detail-header {
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
    }

    .detail-poster-wrapper {
        position: relative;
        width: 100%;
        max-width: 300px;
        margin-bottom: 25px;
    }

    .detail-poster-wrapper img {
        width: 100%;
        height: auto;
        border-radius: 10px;
        box-shadow: 0 8px 20px rgba(0, 0, 0, 0.5);
        border: 3px solid var(--primary-color);
    }

    .detail-genres {
        margin-top: 15px;
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        justify-content: center;
    }

    .genre-tag {
        background: var(--primary-color);
        color: var(--bg-dark);
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 0.9em;
        font-weight: bold;
    }

    .detail-header h1 {
        color: var(--primary-color);
        font-size: 2.8em;
        margin-top: 15px;
        text-shadow: 2px 2px 5px rgba(0,0,0,0.5);
    }

    .detail-meta-info {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 20px;
        margin-top: 20px;
        color: #ccc;
        font-size: 1.1em;
    }

    .detail-meta-info span {
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .detail-meta-info span svg {
        color: var(--primary-color);
    }

    .detail-meta-info .rating {
        color: var(--accent-color);
        font-weight: bold;
    }

    .detail-plot {
        margin-top: 25px;
        color: #c0c0c0;
        font-size: 1.1em;
        text-align: center;
    }

    .detail-buttons {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 20px;
        margin-top: 30px;
    }

    .detail-buttons a {
        display: inline-flex;
        align-items: center;
        gap: 10px;
        background-color: var(--button-bg);
        color: white;
        padding: 14px 30px;
        border-radius: 8px;
        text-decoration: none;
        font-weight: bold;
        font-size: 1.1em;
        transition: background-color 0.3s ease, transform 0.2s ease;
        box-shadow: 0 4px 10px var(--card-shadow);
    }

    .detail-buttons a.telegram { background-color: #0088cc; }
    .detail-buttons a.telegram:hover { background-color: #006699; }
    .detail-buttons a.download { background-color: #28a745; }
    .detail-buttons a.download:hover { background-color: #218838; }
    .detail-buttons a.player { background-color: #dc3545; }
    .detail-buttons a.player:hover { background-color: #c82333; }


    .detail-buttons a:hover {
        transform: translateY(-3px);
    }

    .detail-buttons a svg {
        width: 22px;
        height: 22px;
        fill: currentColor; /* Use button's text color for SVG */
        stroke: currentColor;
    }

    .back-to-home {
        text-align: center;
        margin-top: 40px;
    }

    .back-to-home a {
        color: var(--primary-color);
        text-decoration: none;
        font-weight: bold;
        font-size: 1.1em;
        transition: color 0.2s ease;
    }

    .back-to-home a:hover {
        color: #00b0ff;
        text-decoration: underline;
    }
    
    /* No Movies Found */
    .no-results {
        text-align: center;
        padding: 50px 20px;
        color: #aaa;
        font-size: 1.2em;
    }
    .no-results p {
        margin-bottom: 20px;
    }
    .no-results a {
        color: var(--primary-color);
        text-decoration: none;
        font-weight: bold;
    }
    .no-results a:hover {
        text-decoration: underline;
    }

    /* Admin Styles */
    .admin-container {
        max-width: 900px;
        margin: 50px auto;
        padding: 30px;
        background: var(--bg-medium);
        border-radius: 10px;
        box-shadow: 0 5px 20px var(--card-shadow);
    }
    .admin-container h1, .admin-container h2 {
        color: var(--primary-color);
        text-align: center;
        margin-bottom: 30px;
    }
    .admin-form {
        display: flex;
        flex-direction: column;
        gap: 15px;
    }
    .admin-form label {
        font-weight: bold;
        color: var(--text-color);
        margin-bottom: 5px;
        display: block;
    }
    .admin-form input[type="text"],
    .admin-form input[type="password"],
    .admin-form textarea {
        width: 100%;
        padding: 10px;
        border-radius: 5px;
        border: 1px solid var(--border-color);
        background: var(--bg-light);
        color: var(--text-color);
        font-size: 1em;
        outline: none;
    }
    .admin-form input[type="text"]:focus,
    .admin-form input[type="password"]:focus,
    .admin-form textarea:focus {
        border-color: var(--primary-color);
        box-shadow: 0 0 0 2px rgba(0, 247, 255, 0.3);
    }
    .admin-form button {
        background-color: var(--button-bg);
        color: white;
        padding: 12px 20px;
        border: none;
        border-radius: 5px;
        cursor: pointer;
        font-size: 1.1em;
        font-weight: bold;
        transition: background-color 0.3s ease;
    }
    .admin-form button:hover {
        background-color: var(--button-hover);
    }
    .admin-form .danger-button {
        background-color: var(--danger-color);
    }
    .admin-form .danger-button:hover {
        background-color: #bb2d3b;
    }

    .message {
        padding: 10px;
        margin-bottom: 15px;
        border-radius: 5px;
        font-weight: bold;
    }
    .message.success {
        background-color: #d4edda;
        color: #155724;
        border: 1px solid #c3e6cb;
    }
    .message.error {
        background-color: #f8d7da;
        color: #721c24;
        border: 1px solid #f5c6cb;
    }

    .admin-table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 30px;
    }
    .admin-table th, .admin-table td {
        border: 1px solid var(--border-color);
        padding: 10px;
        text-align: left;
    }
    .admin-table th {
        background-color: var(--bg-light);
        color: var(--primary-color);
    }
    .admin-table td {
        background-color: var(--bg-dark);
        vertical-align: top;
    }
    .admin-table .actions a {
        margin-right: 10px;
        color: var(--button-bg);
    }
    .admin-table .actions a:hover {
        text-decoration: none;
        opacity: 0.8;
    }
    .admin-table .actions form {
        display: inline;
    }
    .admin-table .actions button {
        background: none;
        border: none;
        color: var(--danger-color);
        cursor: pointer;
        font-size: 1em;
        padding: 0;
        text-decoration: underline;
        transition: color 0.2s ease;
    }
    .admin-table .actions button:hover {
        color: #bb2d3b;
    }


    /* Media Queries */
    @media (max-width: 768px) {
        .header-inner {
            flex-wrap: wrap;
            justify-content: center;
        }
        .search-bar {
            order: 3; /* Move search bar to new line */
            flex-basis: 100%;
            margin-top: 15px;
        }
        .logo {
            font-size: 1.5em;
        }
        .menu-icon {
            display: block; /* Show menu icon on small screens */
        }

        .featured-movie {
            height: 300px;
            padding: 20px;
        }
        .featured-content h2 {
            font-size: 1.8em;
        }
        .featured-content p {
            font-size: 0.9em;
            margin-bottom: 15px;
        }
        .featured-actions .watch-btn {
            padding: 10px 20px;
            font-size: 0.9em;
        }

        .section-header h2 {
            font-size: 1.5em;
        }

        .movie-grid {
            grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            gap: 15px;
        }
        .movie-item img {
            height: 220px;
        }
        .movie-item h3 {
            font-size: 1em;
        }

        .detail-container {
            padding: 20px;
            margin: 20px auto;
        }
        .detail-header h1 {
            font-size: 2em;
        }
        .detail-meta-info {
            font-size: 1em;
            gap: 10px;
        }
        .detail-plot {
            font-size: 1em;
        }
        .detail-buttons a {
            padding: 10px 20px;
            font-size: 1em;
            gap: 8px;
        }
    }

    @media (max-width: 480px) {
        .header-inner {
            flex-direction: column;
            align-items: flex-start;
        }
        .logo, .menu-icon {
            width: 100%;
            text-align: center;
        }
        .search-bar {
            width: 100%;
            margin-top: 10px;
        }
        .featured-movie {
            height: 250px;
            align-items: center;
            text-align: center;
            justify-content: center;
        }
        .featured-content {
            max-width: 100%;
        }
        .featured-actions {
            justify-content: center;
        }

        .movie-grid {
            grid-template-columns: 1fr 1fr;
        }
        .detail-buttons {
            flex-direction: column;
            align-items: center;
        }
        .detail-buttons a {
            width: 90%;
            max-width: 300px;
        }
        .admin-table th, .admin-table td {
            font-size: 0.85em;
            padding: 8px;
        }
        .admin-table .actions a, .admin-table .actions button {
            font-size: 0.8em;
        }
    }
    </style>
"""

# --- Home Page ---
@app.route("/")
def home():
    """Renders the home page with a grid of movie posters."""
    try:
        # Fetch all movies, sorted by latest added
        all_movies = list(col.find().sort("_id", -1))
        
        # Determine the featured movie (e.g., the very latest one)
        featured_movie = all_movies[0] if all_movies else None
        
        # Movies for the grid (excluding featured if it's already shown distinctly)
        grid_movies = all_movies[1:] if featured_movie and len(all_movies) > 1 else all_movies

        html = f"""
        <html>
        <head>
            <title>🎬 Movie Zone - Latest Movies</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            {BASE_CSS}
        </head>
        <body>
            {HEADER_HTML}

            <div class="container">
                {{% if featured_movie %}}
                <div class="featured-movie" style="background-image: url('{{{{ featured_movie.poster }}}}');">
                    <div class="featured-content">
                        <h2>{{{{ featured_movie.title }}}}</h2>
                        <p>{{{{ featured_movie.plot }}}}<br>({{ featured_movie.year }})</p>
                        <div class="featured-actions">
                            <a href="/movie/{{{{ featured_movie._id }}}}" class="watch-btn">
                                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="0" stroke-linecap="round" stroke-linejoin="round" class="feather feather-play-circle"><circle cx="12" cy="12" r="10"></circle><polygon points="10 8 16 12 10 16 10 8"></polygon></svg>
                                Watch
                            </a>
                            <span class="rating">
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="0" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>
                                {{{{ featured_movie.rating }}}}
                            </span>
                        </div>
                    </div>
                </div>
                {{% endif %}}

                <div class="section-header">
                    <h2>| LATEST MOVIES</h2>
                    <div class="section-controls">
                        <a href="#">See more</a>
                        <div class="nav-arrows">
                            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>
                            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
                        </div>
                    </div>
                </div>

                {{% if grid_movies %}}
                <div class="movie-grid">
                    {% for m in grid_movies %}
                    <div class="movie-item">
                        <a href="/movie/{{ m._id }}">
                            <img src="{{ m.poster }}" alt="{{ m.title }} Poster"/>
                            <div class="rating-badge">
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="0" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>
                                {{ m.rating }}
                            </div>
                            <div class="movie-item-content">
                                <h3>{{ m.title }}</h3>
                                <p>{{ m.year }}</p>
                                {% if m.language or m.quality %}
                                <div class="movie-tags">
                                    {% if m.quality %}<span class="movie-tag">{{ m.quality }}</span>{% endif %}
                                    {% if m.language %}<span class="movie-tag">{{ m.language.split(',')[0].strip() }}</span>{% endif %}
                                </div>
                                {% endif %}
                            </div>
                        </a>
                    </div>
                    {% endfor %}
                </div>
                {{% else %}}
                <div class="no-results">
                    <p>No movies found yet. Share some movies in your Telegram channel!</p>
                    <p><a href="{{ WEBSITE_URL }}">Refresh Page</a></p>
                </div>
                {{% endif %}}
            </div>
        </body>
        </html>
        """
        return render_template_string(html, movies=grid_movies, featured_movie=featured_movie, request=request)
    except Exception as e:
        logger.error(f"Error rendering Flask home page: {e}")
        return "An internal server error occurred.", 500

# --- Search Page ---
@app.route("/search")
def search():
    query = request.args.get('q', '').strip()
    search_results = []
    if query:
        # Simple case-insensitive search by title
        search_results = list(col.find({"title": {"$regex": query, "$options": "i"}}).sort("_id", -1))
        logger.info(f"Search query: '{query}', Results: {len(search_results)}")

    html = f"""
        <html>
        <head>
            <title>🎬 Search Results for "{{{{ request.args.get('q', '') }}}}"</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            {BASE_CSS}
        </head>
        <body>
            {HEADER_HTML}
            <div class="container">
                <div class="section-header">
                    <h2>| Search Results for "{{{{ request.args.get('q', '') }}}}"</h2>
                </div>

                {{% if search_results %}}
                <div class="movie-grid">
                    {% for m in search_results %}
                    <div class="movie-item">
                        <a href="/movie/{{ m._id }}">
                            <img src="{{ m.poster }}" alt="{{ m.title }} Poster"/>
                            <div class="rating-badge">
                                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="0" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>
                                {{ m.rating }}
                            </div>
                            <div class="movie-item-content">
                                <h3>{{ m.title }}</h3>
                                <p>{{ m.year }}</p>
                                {% if m.language or m.quality %}
                                <div class="movie-tags">
                                    {% if m.quality %}<span class="movie-tag">{{ m.quality }}</span>{% endif %}
                                    {% if m.language %}<span class="movie-tag">{{ m.language.split(',')[0].strip() }}</span>{% endif %}
                                </div>
                                {% endif %}
                            </div>
                        </a>
                    </div>
                    {% endfor %}
                </div>
                {{% else %}}
                <div class="no-results">
                    <p>No movies found matching your search "{{{{ request.args.get('q', '') }}}}".</p>
                    <p><a href="/">Back to Home</a></p>
                </div>
                {{% endif %}}
            </div>
        </body>
        </html>
    """
    return render_template_string(html, search_results=search_results, request=request)


# --- Movie Detail Page ---
@app.route("/movie/<movie_id>")
def movie_detail(movie_id):
    """Renders the detailed page for a single movie."""
    try:
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
            {BASE_CSS}
        </head>
        <body>
            {HEADER_HTML}

            <div class="container detail-container">
                <div class="detail-header">
                    <div class="detail-poster-wrapper">
                        {{% if movie.poster %}}
                        <img src="{{{{ movie.poster }}}}" alt="{{{{ movie.title }}}} Poster"/>
                        {{% else %}}
                        <img src="https://via.placeholder.com/300x450?text=No+Poster" alt="No Poster Available"/>
                        {{% endif %}}
                    </div>
                    {{% if movie.genre %}}
                    <div class="detail-genres">
                        {% for genre in movie.genre.split(', ') %}
                        <span class="genre-tag">{{{{ genre }}}}</span>
                        {% endfor %}
                    </div>
                    {{% endif %}}
                    <h1>{{{{ movie.title }}}}</h1>
                    <div class="detail-meta-info">
                        {{% if movie.runtime %}}
                        <span>
                            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                            {{{{ movie.runtime }}}}
                        </span>
                        {{% endif %}}
                        {{% if movie.year %}}
                        <span>
                            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
                            {{{{ movie.year }}}}
                        </span>
                        {{% endif %}}
                        {{% if movie.language %}}
                        <span>
                            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 3L20 12L5 21V3Z"></path></svg>
                            {{{{ movie.language.split(',')[0].strip() }}}}
                        </span>
                        {{% endif %}}
                        {{% if movie.quality %}}
                        <span>
                            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"></path><path d="M2 17l10 5 10-5"></path><path d="M2 12l10 5 10-5"></path></svg>
                            {{{{ movie.quality }}}}
                        </span>
                        {{% endif %}}
                        {{% if movie.rating %}}
                        <span class="rating">
                            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="0" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>
                            {{{{ movie.rating }}}}
                        </span>
                        {{% endif %}}
                    </div>
                </div>

                <p class="detail-plot">{{{{ movie.plot }}}}</p>

                <div class="detail-buttons">
                    {{% if movie.telegram_link %}}
                        <a href="{{{{ movie.telegram_link }}}}" target="_blank" rel="noopener noreferrer" class="telegram">
                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13M22 2L15 22L11 13L2 9L22 2Z"></path></svg>
                            Telegram
                        </a>
                    {{% endif %}}
                    {{% if movie.file_id %}}
                        <a href="https://t.me/{BOT_USERNAME}?start=get_file_{{{{ movie.file_id }}}}" target="_blank" rel="noopener noreferrer" class="download">
                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                            Download
                        </a>
                    {{% endif %}}
                    {{% if movie.external_watch_link %}}
                        <a href="{{{{ movie.external_watch_link }}}}" target="_blank" rel="noopener noreferrer" class="player">
                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polygon points="10 8 16 12 10 16 10 8"></polygon></svg>
                            Player
                        </a>
                    {{% endif %}}
                </div>

                <div class="section-header">
                    <h2>| YOU MAY ALSO LIKE</h2>
                    <div class="section-controls">
                        <a href="#">See more</a>
                        <div class="nav-arrows">
                            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>
                            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
                        </div>
                    </div>
                </div>
                <div class="movie-grid">
                    <div class="movie-item">
                        <a href="#">
                            <img src="https://via.placeholder.com/180x270?text=Related+Movie+1" alt="Related Movie 1"/>
                            <div class="rating-badge">⭐ N/A</div>
                            <div class="movie-item-content">
                                <h3>Related Movie 1</h3>
                                <p>Year</p>
                                <div class="movie-tags">
                                    <span class="movie-tag">Tag</span>
                                </div>
                            </div>
                        </a>
                    </div>
                     <div class="movie-item">
                        <a href="#">
                            <img src="https://via.placeholder.com/180x270?text=Related+Movie+2" alt="Related Movie 2"/>
                            <div class="rating-badge">⭐ N/A</div>
                            <div class="movie-item-content">
                                <h3>Related Movie 2</h3>
                                <p>Year</p>
                                <div class="movie-tags">
                                    <span class="movie-tag">Tag</span>
                                </div>
                            </div>
                        </a>
                    </div>
                    </div>

                <div class="back-to-home">
                    <a href="/">← Back to Home</a>
                </div>
            </div>
        </body>
        </html>
        """
        return render_template_string(html, movie=movie, BOT_USERNAME=BOT_USERNAME, request=request)
    except Exception as e:
        logger.error(f"Error rendering movie detail page for ID {movie_id}: {e}")
        return "An internal server error occurred.", 500

# ==================== Admin Panel ====================

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            flash('Logged in successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials. Please try again.', 'error')
    
    # Login HTML
    login_html = f"""
    <html>
    <head>
        <title>Admin Login</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        {BASE_CSS}
    </head>
    <body>
        <div class="container admin-container">
            <h1>Admin Login</h1>
            {{% with messages = get_flashed_messages(with_categories=true) %}}
                {{% if messages %}}
                    <ul class="flashes">
                    {{% for category, message in messages %}}
                        <li class="message {{{{ category }}}}">{{{{ message }}}}</li>
                    {{% endfor %}}
                    </ul>
                {{% endif %}}
            {{% endwith %}}
            <form method="post" action="/admin" class="admin-form">
                <label for="username">Username:</label>
                <input type="text" id="username" name="username" required>
                <label for="password">Password:</label>
                <input type="password" id="password" name="password" required>
                <button type="submit">Log In</button>
            </form>
        </div>
    </body>
    </html>
    """
    return render_template_string(login_html)

@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    try:
        movies = list(col.find().sort("_id", -1))
        
        dashboard_html = f"""
        <html>
        <head>
            <title>Admin Dashboard</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            {BASE_CSS}
        </head>
        <body>
            <header class="main-header">
                <div class="header-inner">
                    <a href="/admin/dashboard" class="logo">Admin Panel</a>
                    <nav>
                        <a href="/" style="margin-left: 20px; color: var(--text-color);">View Site</a> |
                        <a href="/admin/logout" style="margin-left: 10px; color: var(--danger-color);">Logout</a>
                    </nav>
                </div>
            </header>

            <div class="container admin-container">
                <h1>Movie Management</h1>
                {{% with messages = get_flashed_messages(with_categories=true) %}}
                    {{% if messages %}}
                        <ul class="flashes">
                        {{% for category, message in messages %}}
                            <li class="message {{{{ category }}}}">{{{{ message }}}}</li>
                        {{% endfor %}}
                        </ul>
                    {{% endif %}}
                {{% endwith %}}

                {{% if movies %}}
                <table class="admin-table">
                    <thead>
                        <tr>
                            <th>Title</th>
                            <th>Year</th>
                            <th>Rating</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {{% for movie in movies %}}
                        <tr>
                            <td>{{{{ movie.title }}}}</td>
                            <td>{{{{ movie.year }}}}</td>
                            <td>{{{{ movie.rating }}}}</td>
                            <td class="actions">
                                <a href="/admin/edit/{{{{ movie._id }}}}">Edit</a>
                                <form action="/admin/delete/{{{{ movie._id }}}}" method="post" onsubmit="return confirm('Are you sure you want to delete this movie?');">
                                    <button type="submit">Delete</button>
                                </form>
                            </td>
                        </tr>
                        {{% endfor %}}
                    </tbody>
                </table>
                {{% else %}}
                <p style="text-align: center; color: #aaa;">No movies in the database yet.</p>
                {{% endif %}}
            </div>
        </body>
        </html>
        """
        return render_template_string(dashboard_html, movies=movies)
    except Exception as e:
        logger.error(f"Error rendering admin dashboard: {e}")
        flash('An error occurred loading dashboard.', 'error')
        return "An internal server error occurred in admin dashboard.", 500

@app.route("/admin/edit/<movie_id>", methods=["GET", "POST"])
@login_required
def admin_edit_movie(movie_id):
    try:
        movie_obj_id = ObjectId(movie_id)
        movie = col.find_one({"_id": movie_obj_id})

        if not movie:
            abort(404)

        if request.method == "POST":
            # Update movie data from form
            updated_data = {
                "title": request.form["title"],
                "year": request.form["year"],
                "language": request.form["language"],
                "rating": request.form["rating"],
                "poster": request.form["poster"],
                "plot": request.form["plot"],
                "genre": request.form.get("genre"),
                "runtime": request.form.get("runtime"),
                "telegram_link": request.form.get("telegram_link"),
                "file_id": request.form.get("file_id"),
                "external_watch_link": request.form.get("external_watch_link"),
                "quality": request.form.get("quality")
            }
            # Remove empty strings for optional fields
            updated_data = {k: v if v else None for k, v in updated_data.items()}
            
            col.update_one({"_id": movie_obj_id}, {"$set": updated_data})
            flash('Movie updated successfully!', 'success')
            logger.info(f"Movie '{movie_id}' updated by admin.")
            return redirect(url_for('admin_dashboard'))

        edit_html = f"""
        <html>
        <head>
            <title>Edit Movie</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            {BASE_CSS}
        </head>
        <body>
            <header class="main-header">
                <div class="header-inner">
                    <a href="/admin/dashboard" class="logo">Admin Panel</a>
                    <nav>
                        <a href="/" style="margin-left: 20px; color: var(--text-color);">View Site</a> |
                        <a href="/admin/logout" style="margin-left: 10px; color: var(--danger-color);">Logout</a>
                    </nav>
                </div>
            </header>

            <div class="container admin-container">
                <h1>Edit Movie: {{{{ movie.title }}}}</h1>
                {{% with messages = get_flashed_messages(with_categories=true) %}}
                    {{% if messages %}}
                        <ul class="flashes">
                        {{% for category, message in messages %}}
                            <li class="message {{{{ category }}}}">{{{{ message }}}}</li>
                        {{% endfor %}}
                        </ul>
                    {{% endif %}}
                {{% endwith %}}
                <form method="post" class="admin-form">
                    <label for="title">Title:</label>
                    <input type="text" id="title" name="title" value="{{{{ movie.title or '' }}}}" required>

                    <label for="year">Year:</label>
                    <input type="text" id="year" name="year" value="{{{{ movie.year or '' }}}}" required>

                    <label for="language">Language:</label>
                    <input type="text" id="language" name="language" value="{{{{ movie.language or '' }}}}" required>

                    <label for="rating">IMDb Rating:</label>
                    <input type="text" id="rating" name="rating" value="{{{{ movie.rating or '' }}}}" required>

                    <label for="poster">Poster URL:</label>
                    <input type="text" id="poster" name="poster" value="{{{{ movie.poster or '' }}}}" required>

                    <label for="plot">Plot:</label>
                    <textarea id="plot" name="plot" rows="5" required>{{{{ movie.plot or '' }}}}</textarea>
                    
                    <label for="genre">Genre (Comma Separated):</label>
                    <input type="text" id="genre" name="genre" value="{{{{ movie.genre or '' }}}}">

                    <label for="runtime">Runtime (e.g., 120 min):</label>
                    <input type="text" id="runtime" name="runtime" value="{{{{ movie.runtime or '' }}}}">

                    <label for="telegram_link">Telegram Link:</label>
                    <input type="text" id="telegram_link" name="telegram_link" value="{{{{ movie.telegram_link or '' }}}}">

                    <label for="file_id">Telegram File ID (for Bot Download):</label>
                    <input type="text" id="file_id" name="file_id" value="{{{{ movie.file_id or '' }}}}">

                    <label for="external_watch_link">External Watch Link (Player):</label>
                    <input type="text" id="external_watch_link" name="external_watch_link" value="{{{{ movie.external_watch_link or '' }}}}">

                    <label for="quality">Quality (e.g., Blu-ray, 1080p):</label>
                    <input type="text" id="quality" name="quality" value="{{{{ movie.quality or '' }}}}">

                    <button type="submit">Save Changes</button>
                    <a href="/admin/dashboard" style="display: block; text-align: center; margin-top: 10px; color: var(--primary-color);">Cancel</a>
                </form>
            </div>
        </body>
        </html>
        """
        return render_template_string(edit_html, movie=movie)
    except Exception as e:
        logger.error(f"Error rendering/processing edit for movie {movie_id}: {e}")
        flash('An error occurred while editing the movie.', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route("/admin/delete/<movie_id>", methods=["POST"])
@login_required
def admin_delete_movie(movie_id):
    try:
        movie_obj_id = ObjectId(movie_id)
        result = col.delete_one({"_id": movie_obj_id})
        if result.deleted_count > 0:
            flash('Movie deleted successfully!', 'success')
            logger.info(f"Movie '{movie_id}' deleted by admin.")
        else:
            flash('Movie not found or could not be deleted.', 'error')
            logger.warning(f"Attempted to delete non-existent movie '{movie_id}'.")
    except Exception as e:
        logger.error(f"Error deleting movie {movie_id}: {e}")
        flash('An error occurred while deleting the movie.', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/logout")
def admin_logout():
    session.pop('logged_in', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('admin_login'))

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

    file_id = None
    if message.video:
        file_id = message.video.file_id
    elif message.document:
        file_id = message.document.file_id
    elif message.audio: # Unlikely for movies, but included for completeness
        file_id = message.audio.file_id
    
    # Extract external_watch_link and quality from caption
    external_watch_link = None
    quality_tag = None
    
    # Regex to find a URL that looks like a watch link (e.g., "Watch: https://...")
    watch_link_match = re.search(r'(?:Watch|Stream|Link|Player):\s*(https?:\/\/[^\s]+)', caption, re.IGNORECASE)
    if watch_link_match:
        external_watch_link = watch_link_match.group(1)

    # Regex to find quality tags like "Blu-ray", "1080p", "720p", "4K" in the caption
    quality_match = re.search(r'\b(Blu-ray|Web-DL|HDRip|1080p|720p|4K|HD|FHD)\b', caption, re.IGNORECASE)
    if quality_match:
        quality_tag = quality_match.group(1)

    # ============ START: Title Cleaning Logic ============
    title_to_search = raw_title_line

    year = None
    year_match = re.search(r'\(?(\d{4})\)?', title_to_search)
    if year_match:
        year = year_match.group(1)
        title_to_search = re.sub(r'[\(\[\.]?' + re.escape(year_match.group(0)) + r'[\)\]\.]?', ' ', title_to_search).strip()

    # Broader patterns to remove to get a cleaner title for OMDb
    patterns_to_remove = [
        r'\b\d{3,4}p\b', r'\b(?:WEB-DL|HDRip|BluRay|DVDRip|BRRip|WEBRip|HDTV|BDRip|Rip)\b',
        r'\b(?:HEVC|x264|x265|AAC|AC3|DD5\.1|DTS|XviD|MP4|MKV|AVI|FLAC|H\.264|H\.265)\b',
        r'\b(?:HQ Line Audio|Line Audio|Dubbed|ESubs|Subbed|TG|www\.[a-z0-9\-\.]+\.(?:com|net|org))\b',
        r'\b(?:Hindi|Bengali|English|Multi|Dual Audio|Org Audio)\b', r'\[.*?\]',
        r'\(.*?\)', r'-\s*\d+', r'\s*[\._-]\s*', r'trailer', r'full movie', r'sample',
        r'\b(?:x264|x265)\b-\w+', r'repack', r'proper', r'uncut', r'extended', r'director\'s cut',
        r'\b(?:truehd|dts-hd|ac3|eac3|doby)\b', r'\b(?:imax|hdr|uhd|4k|fhd|hd)\b',
        r'\bleaked\b', r'[\u0980-\u09FF]+' # Remove Bengali characters
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
        "genre": data.get("Genre"), # Added genre
        "runtime": data.get("Runtime"), # Added runtime
        "telegram_link": f"https://t.me/{CHANNEL.strip('@')}/{message.id}",
        "file_id": file_id,
        "external_watch_link": external_watch_link, # Captured from caption
        "quality": quality_tag # Captured from caption
    }

    try:
        existing_movie = col.find_one({"title": movie_data["title"], "year": movie_data["year"]})
        if existing_movie:
            # Update only specific fields if movie exists
            update_fields = {
                "file_id": file_id,
                "telegram_link": movie_data["telegram_link"],
                "external_watch_link": movie_data["external_watch_link"],
                "quality": movie_data["quality"],
                "poster": movie_data["poster"], # Update poster in case it changed or was missing
                "rating": movie_data["rating"],
                "plot": movie_data["plot"],
                "genre": movie_data["genre"],
                "runtime": movie_data["runtime"],
                "language": movie_data["language"]
            }
            # Only update if new data is not None or empty string, to avoid overwriting with empty values
            update_set = {k: v for k, v in update_fields.items() if v is not None and v != ''}

            if update_set:
                col.update_one(
                    {"_id": existing_movie["_id"]},
                    {"$set": update_set}
                )
                logger.info(f"⚠️ Movie '{movie_data['title']} ({movie_data['year']})' already exists. Updated data.")
            else:
                logger.info(f"⚠️ Movie '{movie_data['title']} ({movie_data['year']})' already exists. No new data to update.")
        else:
            col.insert_one(movie_data)
            logger.info(f"✅ Saved new movie to DB: {movie_data['title']} ({movie_data['year']}) with file_id: {file_id}")
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
