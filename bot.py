import os
import logging
import threading
import asyncio
from urllib.parse import quote_plus

# --- Selenium Imports ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# --- Other imports ---
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
# ... (flask, threading, etc. from previous code)
from flask import Flask
from werkzeug.serving import make_server

# --- Logging and Config (No changes) ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    API_ID, API_HASH, BOT_TOKEN = map(int, [os.environ.get("API_ID")]), os.environ.get("API_HASH"), os.environ.get("BOT_TOKEN")
    PORT = int(os.environ.get("PORT", 8080))
    # ... other configs
except Exception as e:
    logger.critical(f"Config error: {e}")
    exit()

# --- Selenium Setup for Render/Heroku ---
def setup_selenium():
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    # These paths are set by the buildpacks on Render
    chrome_options.binary_location = os.environ.get("GOOGLE_CHROME_BIN")
    
    driver = webdriver.Chrome(executable_path=os.environ.get("CHROMEDRIVER_PATH"), options=chrome_options)
    return driver

# --- The Ultimate Scraper Function ---
async def scrape_mlwbd(query: str):
    links = {}
    driver = None
    try:
        driver = await asyncio.to_thread(setup_selenium)
        search_url = f"https://mlwbd.fyi/search/{quote_plus(query)}"
        logger.info(f"Scraping: {search_url}")
        driver.get(search_url)

        # Find the first search result link
        wait = WebDriverWait(driver, 15)
        first_result = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.search-item a")))
        movie_page_url = first_result.get_attribute("href")
        
        logger.info(f"Found movie page: {movie_page_url}")
        driver.get(movie_page_url)

        # Find all download links (usually in <a> tags with 'button' classes)
        download_buttons = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//a[contains(@class, 'button') and contains(., 'Download')]")))
        
        for button in download_buttons:
            text = button.text.lower()
            href = button.get_attribute("href")
            
            resolution = "Link"
            if "1080p" in text: resolution = "1080p"
            elif "720p" in text: resolution = "720p"
            elif "480p" in text: resolution = "480p"
            
            # This is a simplification; you might need to follow another redirect page
            if href and 'mlwbd' not in href: # Assuming external links are the final ones
                 if resolution not in links:
                    links[resolution] = href

    except TimeoutException:
        logger.warning(f"Timeout while scraping for '{query}'. Page structure might have changed.")
    except NoSuchElementException:
        logger.warning(f"Could not find elements for '{query}'. Site design likely changed.")
    except Exception as e:
        logger.error(f"An unexpected error occurred during scraping: {e}", exc_info=True)
    finally:
        if driver:
            await asyncio.to_thread(driver.quit)
            
    return links

# --- Pyrogram Bot Initialization (No changes) ---
app = Client("ultimate_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
# --- Flask App Setup (No changes) ---
flask_app = Flask(__name__)
@flask_app.route('/')
def health_check(): return "Ultimate bot is alive!", 200

# --- Pyrogram Handlers (Updated to use the new scraper) ---
@app.on_message(filters.text & filters.private & ~filters.command("start"))
async def search_handler(client: Client, message: Message):
    # ... (Force sub code remains the same) ...
    
    query = message.text
    searching_msg = await message.reply_text(f"🔎 **{query}**-এর জন্য ইন্টারনেট অনুসন্ধান চলছে... এটি কিছুটা সময় নিতে পারে।")
    
    try:
        # Use the new powerful scraper
        links = await scrape_mlwbd(query)
        
        if not links:
            await searching_msg.edit_text(f"**`{query}`**-এর জন্য কোনো লিঙ্ক খুঁজে পাওয়া যায়নি। 😟\n\nসম্ভবত আমাদের সোর্সে মুভিটি নেই অথবা সাইটের গঠনে পরিবর্তন এসেছে।")
            return
            
        buttons = [[InlineKeyboardButton(f"🎬 {res}", url=link)] for res, link in links.items()]
        await searching_msg.edit_text(
            f"**`{query}`**-এর জন্য কিছু লিঙ্ক পাওয়া গেছে:",
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error in search_handler: {e}")
        await searching_msg.edit_text("একটি গুরুতর সমস্যা হয়েছে। ডেভেলপারকে জানানো হয়েছে।")

# --- Threading, Bot Start, etc. (No changes from previous Flask version) ---
# ... (The WebServer class and if __name__ == "__main__": block)

class WebServer(threading.Thread):
    def __init__(self, app):
        threading.Thread.__init__(self)
        self.server = make_server('0.0.0.0', PORT, app)
        self.ctx = app.app_context()
        self.ctx.push()
    def run(self):
        logger.info(f"Flask Web Server {PORT} পোর্টে চালু হচ্ছে...")
        self.server.serve_forever()
    def shutdown(self):
        self.server.shutdown()

def run_bot():
    logger.info("Ultimate Pyrogram bot চালু হচ্ছে...")
    app.run()

if __name__ == "__main__":
    web_server_thread = WebServer(flask_app)
    web_server_thread.start()
    run_bot()
    web_server_thread.shutdown()
