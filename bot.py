import os
import logging
import threading
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import UserNotParticipant

import requests
from bs4 import BeautifulSoup
from urllib.parse import unquote

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
    PORT = int(os.environ.get("PORT", 8080))

except (TypeError, ValueError) as e:
    logger.critical(f"প্রয়োজনীয় এনভায়রনমেন্ট ভেরিয়েবল সেট করা হয়নি: {e}")
    exit()

# --- Pyrogram Bot Initialization ---
app = Client("web_server_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- Flask Web Server Setup ---
flask_app = Flask(__name__)

@flask_app.route('/')
def health_check():
    return "আমি সচল আছি! বটটি ব্যাকগ্রাউন্ডে চলছে।", 200

# --- UPDATED HELPER FUNCTION FOR FILEPRESS ---

async def search_movie_links(query: str):
    """
    গুগলে সার্চ করে বিশেষভাবে FilePress বা এই ধরনের সাইটের লিঙ্ক খুঁজে বের করার ফাংশন।
    """
    # আমরা এখন site:filepress.live এবং অন্যান্য কীওয়ার্ড দিয়ে সার্চ করব
    search_query = f'site:filepress.live OR site:filepress.co OR site:filepress.online "{query}" (480p OR 720p OR 1080p)'
    url = f"https://www.google.com/search?q={search_query}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    links = {}
    try:
        response = await asyncio.to_thread(requests.get, url, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href')
            if href.startswith('/url?q='):
                # গুগল সার্চের URL থেকে আসল লিঙ্ক বের করা
                link = unquote(href.split('/url?q=')[1].split('&sa=')[0])
                
                # নিশ্চিত করা যে লিঙ্কটি FilePress-এর
                if 'filepress.' in link:
                    text = a_tag.get_text().lower()
                    
                    # রেজোলিউশন সনাক্ত করার চেষ্টা
                    resolution = "Unknown Quality"
                    if "1080p" in text or "1080p" in link:
                        resolution = "1080p"
                    elif "720p" in text or "720p" in link:
                        resolution = "720p"
                    elif "480p" in text or "480p" in link:
                        resolution = "480p"
                    
                    # ডুপ্লিকেট রেজোলিউশনের লিঙ্ক এড়ানো
                    if resolution not in links:
                        links[resolution] = link
                        # সর্বোচ্চ ৩-৪টি ভিন্ন কোয়ালিটির লিঙ্ক পেলেই যথেষ্ট
                        if len(links) >= 4:
                            break
                            
    except requests.exceptions.RequestException as e:
        logger.error(f"Google search failed for FilePress links: {e}")
    except Exception as e:
        logger.error(f"An unexpected error in search_movie_links: {e}")
        
    return links

# --- Pyrogram Handlers (কোনো পরিবর্তন নেই) ---

@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    # ... আগের মতোই ...
    await message.reply_text("👋 **স্বাগতম!**\n\nআমি FilePress থেকে মুভি লিঙ্ক খুঁজে দিই। আপনার পছন্দের মুভির নাম লিখুন।")

@app.on_message(filters.text & filters.private & ~filters.command("start"))
async def search_handler(client: Client, message: Message):
    # --- Force Subscribe Check ---
    if FORCE_SUB_CHANNEL_USERNAME:
        try:
            member = await client.get_chat_member(chat_id=f"@{FORCE_SUB_CHANNEL_USERNAME}", user_id=message.from_user.id)
            if member.status in [enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.KICKED]: raise UserNotParticipant
        except UserNotParticipant:
            await message.reply_text("বটটি ব্যবহার করতে আমাদের চ্যানেলে যোগ দিন।", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_SUB_CHANNEL_USERNAME}")]]))
            return
        except Exception: pass
    
    query = message.text
    searching_msg = await message.reply_text("🔎 **FilePress-এ অনুসন্ধান চলছে...**")
    try:
        links = await search_movie_links(query)
        if not links:
            await searching_msg.edit_text(f"**`{query}`**-এর জন্য কোনো FilePress লিঙ্ক খুঁজে পাওয়া যায়নি। 😟\n\nঅনুগ্রহ করে অন্য নাম বা বানান পরীক্ষা করে দেখুন।")
            return
            
        buttons = []
        # ফলাফলগুলোকে সাজিয়ে নেওয়া (1080p, 720p, 480p, Unknown)
        sorted_resolutions = sorted(links.keys(), key=lambda x: ('Unknown' in x, x), reverse=True)
        for res in sorted_resolutions:
            buttons.append([InlineKeyboardButton(f"🎬 {res} Link", url=links[res])])

        await searching_msg.edit_text(
            f"**`{query}`**-এর জন্য কিছু FilePress লিঙ্ক পাওয়া গেছে:",
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error in search_handler: {e}")
        await searching_msg.edit_text("একটি সমস্যা হয়েছে। অনুগ্রহ করে আবার চেষ্টা করুন।")


# --- Threading and Main Execution (কোনো পরিবর্তন নেই) ---
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
    logger.info("Pyrogram বট চালু হচ্ছে...")
    app.run()

if __name__ == "__main__":
    web_server_thread = WebServer(flask_app)
    web_server_thread.start()
    run_bot()
    web_server_thread.shutdown()
