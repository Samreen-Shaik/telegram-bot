import os
import requests
import logging
import json
import telebot
import firebase_admin
from firebase_admin import credentials, db
from telebot import TeleBot
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from collections import defaultdict
from pytz import timezone
from datetime import datetime

# Load environment variables
load_dotenv()

# Load API keys
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Initialize bot and scheduler
bot = TeleBot(BOT_TOKEN)
scheduler = BackgroundScheduler()
logging.basicConfig(level=logging.INFO)

# 🔹 Track user points for leaderboard
user_points = defaultdict(int)

# --- 🔥 FIREBASE SETUP ---
cred = credentials.Certificate("firebase_credentials.json")  # Replace with your Firebase credentials file
firebase_admin.initialize_app(cred, {"databaseURL": "https://your-database-url.firebaseio.com"})  # Replace with your DB URL
admin_ref = db.reference("admins")

# --- 🔥 LOAD ADMINS ---
from firebase_admin import firestore

def load_admins():
    """Load admin IDs from Firestore"""
    global ADMIN_IDS
    ADMIN_IDS = set()
    
    try:
        db_ref = firestore.client()
        admins_ref = db_ref.collection("admins")
        admins_docs = admins_ref.stream()

        for doc in admins_docs:
            data = doc.to_dict()
            if data.get("role") == "admin":
                try:
                    admin_id = int(doc.id)  # Convert document ID to integer
                    ADMIN_IDS.add(admin_id)
                except ValueError:
                    print(f"⚠ Skipping invalid admin ID: {doc.id}")  # Skip non-numeric IDs
        
        print("✅ Loaded Admins:", ADMIN_IDS)

    except Exception as e:
        print(f"❌ Error loading admins: {e}")



def save_admins():
    """Save admin IDs to Firebase"""
    try:
        admin_ref.set({str(uid): {"role": "admin"} for uid in ADMIN_IDS})  # Storing as dict
        logging.info(f"✅ Saved admins: {ADMIN_IDS}")  # Debugging
    except Exception as e:
        logging.error(f"❌ Error saving admins: {e}")

# Load admins at startup
load_admins()

@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = """
🤖 **Bot Commands Guide:**
  
📌 **Weather Commands**
  - `/weather <city>` → Get weather details for a city.

📌 **Admin Commands**
  - `/addadmin <ID>` → Add a new admin (Admins only)
  - `/removeadmin <ID>` → Remove an admin (Admins only)

📌 **Leaderboard Commands**
  - `/leaderboard` → Show the top users.

📌 **Announcements**
  - `/schedule Message | YYYY-MM-DD HH:MM:SS` → Schedule a message (Admins only)

📌 **Chat with AI**
  - Simply type a message to chat with the bot.

Use these commands to interact with me! 🚀
    """
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")



# --- 🟢 WEATHER FEATURE ---
@bot.message_handler(commands=['weather'])
def get_weather(message):
    user_id = message.chat.id
    location = message.text.replace("/weather", "").strip()

    if not location:
        bot.send_message(user_id, "⚠ Please provide a city name. Example: `/weather London`")
        return

    url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={WEATHER_API_KEY}&units=metric"

    try:
        response = requests.get(url)
        data = response.json()

        if data.get("cod") != 200:
            bot.send_message(user_id, f"⚠ Error: {data.get('message', 'Unknown error')}")
            return

        weather_info = (
            f"🌍 **Weather in {data['name']}, {data['sys']['country']}**:\n"
            f"🌡 **Temperature**: {data['main']['temp']}°C\n"
            f"☁ **Condition**: {data['weather'][0]['description'].capitalize()}\n"
            f"💧 **Humidity**: {data['main']['humidity']}%\n"
            f"🌬 **Wind Speed**: {data['wind']['speed']} m/s"
        )

        bot.send_message(user_id, weather_info, parse_mode="Markdown")

    except requests.exceptions.RequestException as e:
        logging.error(f"Weather API Error: {e}")
        bot.send_message(user_id, "⚠ Weather service is currently unavailable.")

# --- 🔵 AI CHAT FEATURE ---
def get_ai_response(user_text):
    """Fetch AI response from OpenRouter API with the correct request format"""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "openai/gpt-3.5-turbo",  
        "messages": [{"role": "user", "content": user_text}],  
        "temperature": 0.7  
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        response_json = response.json()

        if response.status_code == 200:
            return response_json["choices"][0]["message"]["content"]
        elif response.status_code == 401:
            return "⚠ Invalid API Key. Please check your OpenRouter API key."
        elif response.status_code == 429:
            return "⚠ OpenRouter API rate limit exceeded. Try again later."
        else:
            return f"⚠ OpenRouter Error: {response_json.get('error', 'Unknown error')}"

    except requests.exceptions.RequestException as e:
        return f"⚠ API Connection Error: {e}"

    except Exception as e:
        return f"⚠ Unexpected Error: {e}"

# --- 🔴 LEADERBOARD FEATURE ---
@bot.message_handler(commands=['leaderboard'])
def show_leaderboard(message):
    user_id = message.chat.id

    if not user_points:
        bot.send_message(user_id, "🏆 No engagement points recorded yet.")
        return

    sorted_users = sorted(user_points.items(), key=lambda x: x[1], reverse=True)
    top_users = sorted_users[:5]

    leaderboard_text = "🏆 **Top 5 Engaged Users**\n\n"
    for i, (user, points) in enumerate(top_users, start=1):
        leaderboard_text += f"{i}. User {user} - {points} points\n"

    bot.send_message(user_id, leaderboard_text, parse_mode="Markdown")

# --- 🔵 ADD/REMOVE ADMIN FEATURE ---
@bot.message_handler(commands=['addadmin'])
def add_admin(message):
    user_id = message.chat.id

    if user_id not in ADMIN_IDS:
        bot.send_message(user_id, "⚠ Only existing admins can add new admins.")
        return

    parts = message.text.strip().split()
    if len(parts) != 2:
        bot.send_message(user_id, "⚠ Invalid format. Use: `/addadmin <Telegram ID>`")
        return

    try:
        new_admin_id = int(parts[1])
    except ValueError:
        bot.send_message(user_id, "⚠ Invalid Telegram ID format.")
        return

    if new_admin_id in ADMIN_IDS:
        bot.send_message(user_id, "⚠ This user is already an admin.")
        return

    ADMIN_IDS.add(new_admin_id)
    save_admins()
    bot.send_message(user_id, f"✅ Admin {new_admin_id} added successfully!")
@bot.message_handler(commands=['removeadmin'])
def remove_admin(message):
    user_id = message.chat.id

    if user_id not in ADMIN_IDS:
        bot.send_message(user_id, "⚠ Only existing admins can remove other admins.")
        return

    parts = message.text.strip().split()
    if len(parts) != 2:
        bot.send_message(user_id, "⚠ Invalid format. Use: `/removeadmin <Telegram ID>`")
        return

    try:
        admin_to_remove = int(parts[1])
    except ValueError:
        bot.send_message(user_id, "⚠ Invalid Telegram ID format.")
        return

    if admin_to_remove not in ADMIN_IDS:
        bot.send_message(user_id, "⚠ Admin ID not found.")
        return

    ADMIN_IDS.remove(admin_to_remove)
    save_admins()
    bot.send_message(user_id, f"✅ Admin {admin_to_remove} removed successfully!")

# --- 🔴 SCHEDULE ANNOUNCEMENTS ---
@bot.message_handler(commands=['schedule'])
def schedule_announcement(message):
    user_id = message.chat.id

    if user_id not in ADMIN_IDS:
        bot.send_message(user_id, "⚠ You are not authorized to schedule announcements.")
        return

    try:
        # Split the message at the first occurrence of "|"
        parts = message.text.split("|", 1)  
        if len(parts) != 2:
            raise ValueError("Invalid format")  

        announcement = parts[0].replace("/schedule", "").strip()  # Extract message
        datetime_str = parts[1].strip()  # Extract date-time string  

        # Convert to datetime object (ensure format is correct)
        dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")

        # Add job to the scheduler
        scheduler.add_job(send_scheduled_announcement, 'date', run_date=dt, args=[announcement])
        
        bot.send_message(user_id, f"✅ Scheduled Announcement: '{announcement}' at {datetime_str}")

    except ValueError:
        bot.send_message(user_id, "⚠ Invalid format. Use: `/schedule Message | YYYY-MM-DD HH:MM:SS`")
    except Exception as e:
        bot.send_message(user_id, f"❌ Error: {e}")

def send_scheduled_announcement(announcement):
    for user_id in user_points.keys():  # Ensure user_points has active users
        try:
            bot.send_message(user_id, f"📢 {announcement}")
            logging.info(f"✅ Sent scheduled announcement to {user_id}")
        except Exception as e:
            logging.error(f"❌ Failed to send message to {user_id}: {e}")

# --- 🔵 AI CHAT HANDLER (Placed Last) ---
@bot.message_handler(func=lambda message: True)
def ai_chat(message):
    user_id = message.chat.id
    user_points[user_id] += 1
    bot_reply = get_ai_response(message.text)
    bot.send_message(user_id, bot_reply)

# --- 🔥 START BOT ---
if __name__ == "__main__":
    logging.info("🤖 Bot is starting...")
    scheduler.start()
    bot.polling()
