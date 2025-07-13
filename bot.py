import os
import logging
import asyncio
import re
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import UserNotParticipant

import requests
from bs4 import BeautifulSoup

# --- Logging Setup ---
# লগিং সেটআপ করা হচ্ছে যাতে সার্ভারে বটের অ্যাক্টিভিটি দেখা যায়
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# --- Configuration from Environment Variables ---
# Render/Heroku-তে Environment Variable হিসেবে এগুলো সেট করতে হবে
try:
    API_ID = int(os.environ.get("API_ID"))
    API_HASH = os.environ.get("API_HASH")
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    
    # (ঐচ্ছিক) ফোর্স সাবস্ক্রাইব চ্যানেল
    FORCE_SUB_CHANNEL_USERNAME = os.environ.get("FORCE_SUB_CHANNEL_USERNAME", None) # যেমন: "MyUpdateChannel"
    
    # (ঐচ্ছিক) এডমিন আইডি
    ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

except (TypeError, ValueError) as e:
    logger.critical(f"প্রয়োজনীয় এনভায়রনমেন্ট ভেরিয়েবল সেট করা হয়নি: {e}")
    exit()

# --- Bot Initialization ---
app = Client("web_server_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


# --- Helper Functions ---

async def search_movie_links(query: str):
    """
    ইন্টারনেটে সার্চ করে মুভির লিঙ্ক খুঁজে বের করার ফাংশন।
    এটি বিভিন্ন সার্চ টার্ম ব্যবহার করে সেরা ফলাফল খোঁজার চেষ্টা করে।
    """
    search_query = f'"{query}" (480p OR 720p OR 1080p) "Google Drive" -site:youtube.com'
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
                link = href.split('/url?q=')[1].split('&sa=')[0]
                if 'drive.google.com' in link:
                    # রেজোলিউশন সনাক্ত করার চেষ্টা
                    text = a_tag.get_text().lower()
                    resolution = "Unknown"
                    if "1080p" in text:
                        resolution = "1080p"
                    elif "720p" in text:
                        resolution = "720p"
                    elif "480p" in text:
                        resolution = "480p"
                    
                    if resolution not in links: # প্রতি রেজোলিউশনে একটি লিঙ্ক রাখা
                        links[resolution] = link
                        if len(links) >= 5: # সর্বোচ্চ ৫টি লিঙ্ক
                            break
                            
    except requests.exceptions.RequestException as e:
        logger.error(f"Google search failed: {e}")
    except Exception as e:
        logger.error(f"An unexpected error in search_movie_links: {e}")
        
    return links

# --- Message Handlers ---

@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    """/start কমান্ডের জন্য হ্যান্ডলার"""
    await message.reply_text(
        "👋 **স্বাগতম!**\n\n"
        "আমি একটি অটোমেটিক মুভি সার্চ বট। আপনার পছন্দের মুভির নাম লিখুন, আমি ইন্টারনেট থেকে তার গুগল ড্রাইভ লিঙ্ক খুঁজে দেওয়ার চেষ্টা করব।\n\n"
        f"개발자: [Developer Name](tg://user?id={ADMIN_ID})" # এখানে আপনার নাম ও আইডি দিতে পারেন
    )

@app.on_message(filters.text & filters.private & ~filters.command("start"))
async def search_handler(client: Client, message: Message):
    """ইউজারের টেক্সট মেসেজ হ্যান্ডেল করে"""

    # --- Force Subscribe Check (ঐচ্ছিক) ---
    if FORCE_SUB_CHANNEL_USERNAME:
        try:
            member = await client.get_chat_member(chat_id=f"@{FORCE_SUB_CHANNEL_USERNAME}", user_id=message.from_user.id)
            if member.status in [enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.KICKED]:
                raise UserNotParticipant
        except UserNotParticipant:
            join_url = f"https://t.me/{FORCE_SUB_CHANNEL_USERNAME}"
            await message.reply_text(
                "ക്ഷമിക്കണം! ഈ ബോട്ട് ഉപയോഗിക്കുന്നതിന് നിങ്ങൾ ഞങ്ങളുടെ ചാനലിൽ ചേരേണ്ടതുണ്ട്.\n\n"
                "ദയവായി ഞങ്ങളുടെ ചാനലിൽ ചേരുക, തുടർന്ന് വീണ്ടും ശ്രമിക്കുക.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 Join Channel", url=join_url)]])
            )
            return
        except Exception as e:
            logger.error(f"Force sub check failed: {e}")
            pass # কোনো কারণে চেক করতে না পারলে সার্চ করতে দেওয়া

    query = message.text
    searching_msg = await message.reply_text("🔎 **অনুসন্ধান চলছে...**\n\nঅনুগ্রহ করে কিছুক্ষণ অপেক্ষা করুন, আমি আপনার জন্য সেরা লিঙ্কটি খুঁজে বের করছি।")
    
    try:
        links = await search_movie_links(query)

        if not links:
            await searching_msg.edit_text(f"**`{query}`**-এর জন্য কোনো গুগল ড্রাইভ লিঙ্ক খুঁজে পাওয়া যায়নি। 😟\n\nঅনুগ্রহ করে নাম সঠিকভাবে লিখে আবার চেষ্টা করুন।")
            return

        buttons = []
        for resolution, link in links.items():
            buttons.append([InlineKeyboardButton(f"🎬 {resolution} Link", url=link)])

        await searching_msg.edit_text(
            f"**`{query}`**-এর জন্য কিছু লিঙ্ক পাওয়া গেছে:",
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )

    except Exception as e:
        logger.error(f"Error in search_handler for query '{query}': {e}")
        await searching_msg.edit_text("একটি সমস্যা হয়েছে। অনুগ্রহ করে কিছুক্ষণ পর আবার চেষ্টা করুন।")

# --- Bot Start ---
if __name__ == "__main__":
    logger.info("Bot is starting...")
    app.run()
    logger.info("Bot has stopped.")
