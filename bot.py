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

# --- Pyrogram Imports ---
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import UserNotParticipant

# --- Flask Imports for Web Service ---
from flask import Flask
from werkzeug.serving import make_server

# --- Logging Configuration ---
# সার্ভারে ডিবাগিং এর জন্য লগিং সেটআপ
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# --- Environment Variable Configuration ---
# Render/Heroku থেকে এনভায়রনমেন্ট ভেরিয়েবল লোড করা হচ্ছে
try:
    API_ID = int(os.environ.get("API_ID"))
    API_HASH = os.environ.get("API_HASH")
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    
    # Render স্বয়ংক্রিয়ভাবে PORT এনভায়রনমেন্ট ভেরিয়েবল সেট করে
    PORT = int(os.environ.get("PORT", "8080"))

    # ঐচ্ছিক ভেরিয়েবল
    FORCE_SUB_CHANNEL_USERNAME = os.environ.get("FORCE_SUB_CHANNEL_USERNAME", None)
    ADMIN_ID = os.environ.get("ADMIN_ID", None)
    if ADMIN_ID:
        try:
            ADMIN_ID = int(ADMIN_ID)
        except ValueError:
            logger.warning("ADMIN_ID environment variable is not a valid integer. Ignoring.")
            ADMIN_ID = None

except (TypeError, ValueError) as e:
    logger.critical(f"কনফিগারেশনে ত্রুটি: API_ID, API_HASH, BOT_TOKEN সঠিকভাবে সেট করা হয়নি। Error: {e}")
    exit(1)
except Exception as e:
    logger.critical(f"একটি অপ্রত্যাশিত কনফিগারেশন ত্রুটি ঘটেছে: {e}")
    exit(1)


# --- Selenium Setup for Render Environment ---
def setup_selenium_driver():
    """Render-এর জন্য Selenium WebDriver সেটআপ করে।"""
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    # Buildpack দ্বারা এই পাথগুলো সেট করা হয়
    chrome_options.binary_location = os.environ.get("GOOGLE_CHROME_BIN")
    
    driver = webdriver.Chrome(executable_path=os.environ.get("CHROMEDRIVER_PATH"), options=chrome_options)
    logger.info("Selenium WebDriver successfully configured.")
    return driver


# --- The Ultimate Scraper Function using Selenium ---
async def scrape_movie_links_from_source(query: str):
    """MLWBD বা অনুরূপ সাইট থেকে মুভি লিঙ্ক স্ক্র্যাপ করে।"""
    links = {}
    driver = None
    try:
        driver = await asyncio.to_thread(setup_selenium_driver)
        # MLWBD-এর সার্চ URL, প্রয়োজন হলে অন্য সাইটের জন্য পরিবর্তনযোগ্য
        search_url = f"https://mlwbd.fyi/search/{quote_plus(query)}"
        logger.info(f"Scraping started for query '{query}' at URL: {search_url}")
        driver.get(search_url)

        # সার্চ ফলাফলের প্রথম লিঙ্কটি খুঁজে বের করা
        wait = WebDriverWait(driver, 20) # টাইমআউট বাড়ানো হয়েছে
        first_result_link_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.search-item a")))
        movie_page_url = first_result_link_element.get_attribute("href")
        
        logger.info(f"Found movie page: {movie_page_url}")
        driver.get(movie_page_url)

        # ডাউনলোড লিঙ্ক বাটনগুলো খুঁজে বের করা
        download_buttons = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//a[contains(@class, 'button') or contains(@class, 'btn')]")))
        
        for button in download_buttons:
            text = button.text.lower()
            href = button.get_attribute("href")
            
            # লিঙ্কটি কার্যকর এবং বাহ্যিক কিনা তা পরীক্ষা করা
            if href and not href.startswith("#") and "mlwbd" not in href:
                resolution = "Link"
                if "1080p" in text: resolution = "1080p"
                elif "720p" in text: resolution = "720p"
                elif "480p" in text: resolution = "480p"
                
                if resolution not in links: # ডুপ্লিকেট রেজোলিউশন এড়ানো
                    links[resolution] = href
                    logger.info(f"Found link: {resolution} -> {href}")

    except TimeoutException:
        logger.warning(f"Timeout while scraping for '{query}'. The page might be too slow or the structure has changed.")
    except NoSuchElementException:
        logger.warning(f"Could not find required elements for '{query}'. Site design has likely changed.")
    except Exception as e:
        logger.error(f"An unexpected error occurred during scraping: {e}", exc_info=True)
    finally:
        if driver:
            await asyncio.to_thread(driver.quit)
            logger.info("Selenium WebDriver closed.")
            
    return links


# --- Pyrogram Bot and Flask App Initialization ---
app = Client("ultimate_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    """Render-কে জানানোর জন্য যে অ্যাপটি সচল আছে"""
    return "Movie Scraper Bot is alive and running!", 200


# --- Pyrogram Message Handlers ---
@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    """/start কমান্ডের জন্য হ্যান্ডলার"""
    await message.reply_text(
        "👋 **স্বাগতম!**\n\n"
        "আমি একটি শক্তিশালী মুভি সার্চ বট। আপনার পছন্দের মুভির নাম লিখুন, আমি ইন্টারনেট থেকে তার ডাউনলোড লিঙ্ক খুঁজে দেওয়ার চেষ্টা করব।\n\n"
        "অনুগ্রহ করে মনে রাখবেন, সার্চ করতে কিছুটা সময় লাগতে পারে।"
    )

@app.on_message(filters.text & filters.private & ~filters.command("start"))
async def search_handler(client: Client, message: Message):
    """ইউজারের টেক্সট মেসেজ হ্যান্ডেল করে এবং স্ক্র্যাপার চালায়"""
    
    # --- ফোর্স সাবস্ক্রাইব চেক ---
    if FORCE_SUB_CHANNEL_USERNAME:
        try:
            member = await client.get_chat_member(chat_id=f"@{FORCE_SUB_CHANNEL_USERNAME}", user_id=message.from_user.id)
            if member.status in [enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.KICKED]:
                raise UserNotParticipant
        except UserNotParticipant:
            await message.reply_text(
                "বটটি ব্যবহার করার জন্য আপনাকে আমাদের চ্যানেলে যোগ দিতে হবে।\n\n"
                "দয়াকরে চ্যানেলে যোগ দিয়ে আবার চেষ্টা করুন।",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_SUB_CHANNEL_USERNAME}")]]))
            return
        except Exception as e:
            logger.warning(f"Force sub check failed: {e}")

    query = message.text
    searching_msg = await message.reply_text(f"🔎 **`{query}`**-এর জন্য ইন্টারনেট অনুসন্ধান চলছে...\n\nএই প্রক্রিয়াটি ২০-৩০ সেকেন্ড সময় নিতে পারে। অনুগ্রহ করে ধৈর্য ধরুন।")
    
    try:
        links = await scrape_movie_links_from_source(query)
        
        if not links:
            await searching_msg.edit_text(f"**`{query}`**-এর জন্য কোনো ডাউনলোড লিঙ্ক খুঁজে পাওয়া যায়নি। 😟\n\nসম্ভবত আমাদের সোর্সে মুভিটি নেই অথবা সাইটের গঠনে কোনো পরিবর্তন এসেছে।")
            return
            
        buttons = []
        sorted_resolutions = sorted(links.keys(), key=lambda x: ('Link' in x, x), reverse=True)
        for res in sorted_resolutions:
            buttons.append([InlineKeyboardButton(f"🎬 {res}", url=links[res])])

        await searching_msg.edit_text(
            f"**`{query}`**-এর জন্য কিছু লিঙ্ক পাওয়া গেছে:",
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error in search_handler: {e}", exc_info=True)
        await searching_msg.edit_text("একটি গুরুতর সমস্যা হয়েছে। অনুগ্রহ করে কিছুক্ষণ পর আবার চেষ্টা করুন।")


# --- Threading & Main Execution for Web Service ---
class WebServer(threading.Thread):
    def __init__(self, app):
        threading.Thread.__init__(self)
        self.server = make_server('0.0.0.0', PORT, app)
        self.ctx = app.app_context()
        self.ctx.push()

    def run(self):
        logger.info(f"Flask Web Server is starting on port {PORT}")
        self.server.serve_forever()

    def shutdown(self):
        self.server.shutdown()

def run_pyrogram_bot():
    logger.info("Pyrogram bot is starting...")
    app.run()

if __name__ == "__main__":
    web_server_thread = WebServer(flask_app)
    web_server_thread.start()
    
    run_pyrogram_bot()
    
    web_server_thread.shutdown()
