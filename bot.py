import os
import logging
import threading
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import UserNotParticipant

import requests
from bs4 import BeautifulSoup

from flask import Flask
from werkzeug.serving import make_server

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# --- Configuration from Environment Variables ---
try:
    API_ID = int(os.environ.get("API_ID"))
    API_HASH = os.environ.get("API_HASH")
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    
    FORCE_SUB_CHANNEL_USERNAME = os.environ.get("FORCE_SUB_CHANNEL_USERNAME", None)
    ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
    
    # Render automatically sets the PORT environment variable for Web Services
    PORT = int(os.environ.get("PORT", 8080))

except (TypeError, ValueError) as e:
    logger.critical(f"প্রয়োজনীয় এনভায়রনমেন্ট ভেরিয়েবল সেট করা হয়নি: {e}")
    exit()

# --- Pyrogram Bot Initialization ---
app = Client("web_server_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


# --- Flask Web Server Setup ---
# এটি একটি সাধারণ ওয়েব সার্ভার যা Render-এর Health Check-কে সন্তুষ্ট করবে
flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    """Render-কে জানানোর জন্য যে আমাদের অ্যাপটি সচল আছে"""
    return "আমি সচল আছি! বটটি ব্যাকগ্রাউন্ডে চলছে।", 200

# --- Pyrogram Handlers (কোনো পরিবর্তন নেই) ---

@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    await message.reply_text(
        "👋 **স্বাগতম!**\n\n"
        "আমি একটি অটোমেটিক মুভি সার্চ বট। আপনার পছন্দের মুভির নাম লিখুন।\n\n"
        f"개발자: [Developer Name](tg://user?id={ADMIN_ID})"
    )

async def search_movie_links(query: str):
    # ... (এই ফাংশনটি আগের মতোই থাকবে, কোনো পরিবর্তন নেই) ...
    search_query = f'"{query}" (480p OR 720p OR 1080p) "Google Drive" -site:youtube.com'
    url = f"https://www.google.com/search?q={search_query}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    links = {}
    try:
        response = await asyncio.to_thread(requests.get, url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href')
            if href.startswith('/url?q='):
                link = href.split('/url?q=')[1].split('&sa=')[0]
                if 'drive.google.com' in link:
                    text = a_tag.get_text().lower()
                    resolution = "Unknown"
                    if "1080p" in text: resolution = "1080p"
                    elif "720p" in text: resolution = "720p"
                    elif "480p" in text: resolution = "480p"
                    if resolution not in links:
                        links[resolution] = link
                        if len(links) >= 5: break
    except Exception as e:
        logger.error(f"Google search failed: {e}")
    return links

@app.on_message(filters.text & filters.private & ~filters.command("start"))
async def search_handler(client: Client, message: Message):
    # ... (এই হ্যান্ডলারটিও আগের মতোই থাকবে, কোনো পরিবর্তন নেই) ...
    if FORCE_SUB_CHANNEL_USERNAME:
        try:
            member = await client.get_chat_member(chat_id=f"@{FORCE_SUB_CHANNEL_USERNAME}", user_id=message.from_user.id)
            if member.status in [enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.KICKED]: raise UserNotParticipant
        except UserNotParticipant:
            await message.reply_text("বটটি ব্যবহার করতে আমাদের চ্যানেলে যোগ দিন।", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_SUB_CHANNEL_USERNAME}")]]))
            return
        except Exception: pass
    
    query = message.text
    searching_msg = await message.reply_text("🔎 **অনুসন্ধান চলছে...**")
    try:
        links = await search_movie_links(query)
        if not links:
            await searching_msg.edit_text(f"**`{query}`**-এর জন্য কোনো লিঙ্ক পাওয়া যায়নি। 😟")
            return
        buttons = [[InlineKeyboardButton(f"🎬 {res} Link", url=link)] for res, link in links.items()]
        await searching_msg.edit_text(f"**`{query}`**-এর জন্য লিঙ্ক পাওয়া গেছে:", reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Error in search_handler: {e}")
        await searching_msg.edit_text("একটি সমস্যা হয়েছে।")


# --- Threading and Main Execution ---
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
    """Pyrogram বটটি চালানোর জন্য ফাংশন"""
    logger.info("Pyrogram বট চালু হচ্ছে...")
    app.run()

if __name__ == "__main__":
    # ওয়েব সার্ভারটি একটি আলাদা থ্রেডে চালু করা হচ্ছে
    web_server_thread = WebServer(flask_app)
    web_server_thread.start()
    
    # মূল থ্রেডে বটটি চালানো হচ্ছে
    run_bot()
    
    # বট বন্ধ হলে ওয়েব সার্ভারও বন্ধ করা
    web_server_thread.shutdown()
