import os
import sqlite3
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import aiohttp
from flask import Flask, render_template_string, request, redirect, url_for
from threading import Thread
import signal
import sys

TELEGRAM_TOKEN = "YOUR_BOT_TOKEN"
FCSAPI_KEY = ""
SUPPORT_USERNAME = "iyadbakri"
SUPPORT_PHONE = "+79522677714"
MAX_FREE_ALERTS = 3

CRYPTO_SYMBOLS = ['BTC', 'ETH', 'BNB', 'SOL', 'XRP', 'DOGE', 'ADA']
FOREX_SYMBOLS = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'NZDUSD', 'XAUUSD']

CRYPTO_IDS = {
    'BTC': 'bitcoin', 'ETH': 'ethereum', 'BNB': 'binancecoin',
    'SOL': 'solana', 'XRP': 'ripple', 'DOGE': 'dogecoin', 'ADA': 'cardano'
}

# ========== Database ==========
def init_db():
    conn = sqlite3.connect('alerts.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            is_premium INTEGER DEFAULT 0,
            premium_until TIMESTAMP,
            created_at TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            asset_type TEXT,
            symbol TEXT,
            target_price REAL,
            direction TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ DB ready")

def save_user(user_id, username):
    conn = sqlite3.connect('alerts.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, created_at) VALUES (?, ?, ?)",
              (user_id, username, datetime.now()))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('alerts.db')
    c = conn.cursor()
    c.execute("SELECT user_id, username, is_premium, premium_until FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def upgrade_user(user_id, days=30):
    conn = sqlite3.connect('alerts.db')
    c = conn.cursor()
    premium_until = datetime.now() + timedelta(days=days)
    c.execute("UPDATE users SET is_premium = 1, premium_until = ? WHERE user_id = ?", (premium_until, user_id))
    conn.commit()
    conn.close()
    print(f"✅ User {user_id} upgraded to Premium until {premium_until}")

def downgrade_user(user_id):
    conn = sqlite3.connect('alerts.db')
    c = conn.cursor()
    c.execute("UPDATE users SET is_premium = 0, premium_until = NULL WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    print(f"⚠️ User {user_id} downgraded to Free")

def get_active_alerts_count(user_id):
    conn = sqlite3.connect('alerts.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM alerts WHERE user_id = ? AND is_active = 1", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

def save_alert(user_id, asset_type, symbol, target_price, direction):
    conn = sqlite3.connect('alerts.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO alerts (user_id, asset_type, symbol, target_price, direction, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, asset_type, symbol, target_price, direction, datetime.now()))
    conn.commit()
    conn.close()

def get_user_alerts(user_id):
    conn = sqlite3.connect('alerts.db')
    c = conn.cursor()
    c.execute('SELECT id, asset_type, symbol, target_price, direction FROM alerts WHERE user_id = ? AND is_active = 1', (user_id,))
    alerts = c.fetchall()
    conn.close()
    return alerts

def deactivate_alert(alert_id):
    conn = sqlite3.connect('alerts.db')
    c = conn.cursor()
    c.execute("UPDATE alerts SET is_active = 0 WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()

def get_all_users_for_dashboard():
    conn = sqlite3.connect('alerts.db')
    c = conn.cursor()
    c.execute('''
        SELECT u.user_id, u.username, u.is_premium, u.premium_until, u.created_at,
               (SELECT COUNT(*) FROM alerts WHERE user_id = u.user_id AND is_active = 1) as alerts_count
        FROM users u ORDER BY u.created_at DESC
    ''')
    users = c.fetchall()
    conn.close()
    result = []
    now = datetime.now()
    for user in users:
        days_left = None
        start_date = None
        warning = ""
        if user[2] == 1 and user[3]:
            expiry = datetime.fromisoformat(user[3])
            days_left = (expiry - now).days
            start_date = expiry - timedelta(days=30)
            if days_left < 0:
                warning = "🔴 Expired - Please contact support to renew"
            elif days_left <= 3:
                warning = f"🟡 Expires in {days_left} days - Renewal reminder"
            elif days_left <= 7:
                warning = f"🟢 Expires in {days_left} days"
            else:
                warning = f"✅ Active - {days_left} days remaining"
        result.append({
            'user_id': user[0],
            'username': user[1],
            'is_premium': user[2],
            'premium_until': user[3],
            'start_date': start_date.strftime('%Y-%m-%d') if start_date else None,
            'created_at': user[4],
            'alerts_count': user[5],
            'days_left': days_left,
            'warning': warning
        })
    return result

def get_stats():
    conn = sqlite3.connect('alerts.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1")
    premium_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM alerts WHERE is_active = 1")
    active_alerts = c.fetchone()[0]
    conn.close()
    return total_users, premium_users, active_alerts

# ========== Price Fetching ==========
async def get_crypto_price(symbol):
    try:
        coin_id = CRYPTO_IDS.get(symbol)
        if not coin_id:
            return None
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get(coin_id, {}).get('usd')
    except:
        pass
    return None

async def get_crypto_price_fallback(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    price = float(data['price'])
                    print(f"✅ [Binance] {symbol} = {price}")
                    return price
    except:
        pass
    try:
        url = f"https://api.kraken.com/0/public/Ticker?pair={symbol}USD"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    for pair, values in data.get('result', {}).items():
                        price = float(values['c'][0])
                        print(f"✅ [Kraken] {symbol} = {price}")
                        return price
    except:
        pass
    return None

async def get_forex_price(symbol):
    if FCSAPI_KEY:
        try:
            if symbol == 'XAUUSD':
                url = f"https://fcsapi.com/api-v3/commodity/latest?symbol={symbol}&type=commodity&access_key={FCSAPI_KEY}"
            else:
                url = f"https://fcsapi.com/api-v3/forex/latest?symbol={symbol}&access_key={FCSAPI_KEY}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('status') and data.get('response'):
                            price = float(data['response'][0]['price'])
                            print(f"✅ [FCS API] {symbol} = {price}")
                            return price
        except:
            pass
    
    try:
        if symbol == 'XAUUSD':
            url = "https://api.exchangerate.host/convert?from=XAU&to=USD"
        elif symbol == 'EURUSD':
            url = "https://api.exchangerate.host/convert?from=EUR&to=USD"
        elif symbol == 'GBPUSD':
            url = "https://api.exchangerate.host/convert?from=GBP&to=USD"
        elif symbol == 'USDJPY':
            url = "https://api.exchangerate.host/convert?from=USD&to=JPY"
        else:
            from_currency = symbol[:3]
            to_currency = symbol[3:]
            url = f"https://api.exchangerate.host/convert?from={from_currency}&to={to_currency}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'result' in data:
                        price = float(data['result'])
                        print(f"✅ [ExchangeRate.host] {symbol} = {price}")
                        return price
    except:
        pass
    
    if symbol != 'XAUUSD':
        try:
            from_currency = symbol[:3]
            to_currency = symbol[3:]
            url = f"https://api.frankfurter.app/latest?from={from_currency}&to={to_currency}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'rates' in data and to_currency in data['rates']:
                            price = float(data['rates'][to_currency])
                            print(f"✅ [Frankfurter] {symbol} = {price}")
                            return price
        except:
            pass
    
    if symbol == 'XAUUSD':
        try:
            url = "https://api.coingecko.com/api/v3/simple/price?ids=tether-gold&vs_currencies=usd"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'tether-gold' in data:
                            price = float(data['tether-gold']['usd'])
                            print(f"✅ [CoinGecko] XAUUSD = {price}")
                            return price
        except:
            pass
    
    print(f"❌ All sources failed for {symbol}")
    return None

async def get_price_with_fallback(asset_type, symbol):
    if asset_type == 'crypto':
        price = await get_crypto_price(symbol)
        if not price:
            price = await get_crypto_price_fallback(symbol)
        return price
    else:
        return await get_forex_price(symbol)

DASHBOARD_HTML = '''
<!DOCTYPE html>
<html dir="ltr" lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BRIDGES Dashboard</title>
    <style>

* { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #f0f2f5; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { color: #1a1a2e; margin-bottom: 20px; text-align: center; }
        .stats { display: flex; gap: 20px; margin-bottom: 30px; flex-wrap: wrap; }
        .stat-card { background: white; border-radius: 15px; padding: 20px; flex: 1; min-width: 150px; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .stat-card h3 { color: #666; font-size: 14px; margin-bottom: 10px; }
        .stat-card .number { font-size: 32px; font-weight: bold; color: #1a1a2e; }
        table { width: 100%; background: white; border-radius: 15px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        th { background: #1a1a2e; color: white; padding: 12px; text-align: left; }
        td { padding: 12px; border-bottom: 1px solid #eee; }
        .premium-badge { background: #4CAF50; color: white; padding: 4px 10px; border-radius: 20px; font-size: 12px; }
        .free-badge { background: #ff9800; color: white; padding: 4px 10px; border-radius: 20px; font-size: 12px; }
        .upgrade-btn { background: #2196F3; color: white; border: none; padding: 6px 12px; border-radius: 8px; cursor: pointer; font-size: 12px; }
        .upgrade-btn:hover { background: #0b7dda; }
        .downgrade-btn { background: #dc3545; color: white; border: none; padding: 6px 12px; border-radius: 8px; cursor: pointer; font-size: 12px; margin-left: 5px; }
        .downgrade-btn:hover { background: #c82333; }
        .refresh-btn { background: #4CAF50; color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; margin-bottom: 20px; }
        .refresh-btn:hover { background: #45a049; }
        .expired { color: #dc3545; font-size: 12px; }
        .active { color: #4CAF50; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 BRIDGES Dashboard</h1>
        <div class="stats">
            <div class="stat-card"><h3>👥 Total Users</h3><div class="number">{{ total_users }}</div></div>
            <div class="stat-card"><h3>⭐ Premium Users</h3><div class="number">{{ premium_users }}</div></div>
            <div class="stat-card"><h3>🔔 Active Alerts</h3><div class="number">{{ active_alerts }}</div></div>
        </div>
        <form method="get"><button type="submit" class="refresh-btn">🔄 Refresh</button></form>
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Username</th>
                    <th>Status</th>
                    <th>Alerts</th>
                    <th>Start Date</th>
                    <th>End Date</th>
                    <th>Days Left</th>
                    <th>Details</th>
                    <th>Action</th>
                <tr>
            </thead>
            <tbody>
                {% for user in users %}
                <tr>
                    <td>{{ user.user_id }}</td>
                    <td>@{{ user.username or 'Unknown' }}</td>
                    <td>
                        {% if user.is_premium %}
                            <span class="premium-badge">⭐ Premium</span>
                        {% else %}
                            <span class="free-badge">📋 Free</span>
                        {% endif %}
                    </td>
                    <td>{{ user.alerts_count }} / {% if user.is_premium %}∞{% else %}{{ max_free }}{% endif %}</td>
                    <td>{{ user.start_date or '-' }}</td>
                    <td>{{ user.premium_until[:10] if user.premium_until else '-' }}</td>
                    <td>
                        {% if user.days_left is not none %}
                        {% if user.days_left < 0 %}
                                <span class="expired">0 (Expired)</span>
                            {% else %}
                                <span class="active">{{ user.days_left }} days</span>
                            {% endif %}
                        {% else %}
                            -
                        {% endif %}
                    </td>
                    <td>{{ user.warning or '-' }}</td>
                    <td>
                        {% if not user.is_premium %}
                            <form method="post" style="display:inline;">
                                <input type="hidden" name="upgrade_id" value="{{ user.user_id }}">
                                <button type="submit" class="upgrade-btn">⭐ Upgrade</button>
                            </form>
                        {% else %}
                            <form method="post" style="display:inline;">
                                <input type="hidden" name="downgrade_id" value="{{ user.user_id }}">
                                <button type="submit" class="downgrade-btn" onclick="return confirm('Downgrade this user?')">⛔ Downgrade</button>
                            </form>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
'''

web_app = Flask(__name__)

@web_app.route('/', methods=['GET', 'POST'])
def dashboard():
    if request.method == 'POST':
        upgrade_id = request.form.get('upgrade_id')
        downgrade_id = request.form.get('downgrade_id')
        if upgrade_id:
            upgrade_user(int(upgrade_id))
            return redirect(url_for('dashboard'))
        if downgrade_id:
            downgrade_user(int(downgrade_id))
            return redirect(url_for('dashboard'))
    users = get_all_users_for_dashboard()
    total_users, premium_users, active_alerts = get_stats()
    return render_template_string(DASHBOARD_HTML, 
                                  users=users, 
                                  total_users=total_users, 
                                  premium_users=premium_users, 
                                  active_alerts=active_alerts, 
                                  max_free=MAX_FREE_ALERTS,
                                  now=datetime.now().isoformat())

def run_web_server():
    web_app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

Thread(target=run_web_server, daemon=True).start()

# ========== Bot Menus ==========
def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("➕ Add Alert", callback_data="add_alert")],
        [InlineKeyboardButton("📋 My Alerts", callback_data="my_alerts")],
        [InlineKeyboardButton("💰 Prices", callback_data="prices")],
        [InlineKeyboardButton("⭐ My Plan", callback_data="myplan")],
        [InlineKeyboardButton("📞 Support", callback_data="support")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_asset_type_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("₿ Crypto", callback_data="asset_crypto")],
        [InlineKeyboardButton("💱 Forex", callback_data="asset_forex")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])

def get_crypto_menu():
    keyboard = []
    row = []
    for sym in CRYPTO_SYMBOLS:
        row.append(InlineKeyboardButton(sym, callback_data=f"crypto_{sym}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("✏️ Custom", callback_data="custom_crypto")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_asset")])
    return InlineKeyboardMarkup(keyboard)

def get_forex_menu():
    keyboard = []
    row = []
    for sym in FOREX_SYMBOLS:
        row.append(InlineKeyboardButton(sym, callback_data=f"forex_{sym}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("✏️ Custom", callback_data="custom_forex")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_asset")])
    return InlineKeyboardMarkup(keyboard)

def get_cancel_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel")]])

# ========== Bot Handlers ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username)
    await update.message.reply_text(
        "🚀 *BRIDGES - Crypto & Forex Alert Bot*\n\n"
        "Monitor prices and receive instant alerts!\n\n"
        "• Free plan: 3 active alerts\n"
        "• Premium: Unlimited alerts ($5/month)\n\n"
        "Choose an option:",
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "cancel":
        context.user_data.clear()
        await query.edit_message_text("❌ Cancelled.", reply_markup=get_main_menu())
        return

    if data == "support":
        await query.edit_message_text(
            f"📞 *Support & Premium Upgrade*\n\n"
            f"⭐ *Upgrade to Premium:*\n"
            f"💰 *Price:* $5/month\n"
            f"✨ *Benefits:* Unlimited alerts + Priority support\n\n"
            f"📱 *Contact us to upgrade:*\n"
            f"• WhatsApp: {SUPPORT_PHONE}\n"
            f"• Telegram: @{SUPPORT_USERNAME}\n\n"
            f"🕒 *Hours:* 9AM - 5PM (Friday off)\n\n"
            f"_After payment, your account will be activated within minutes_",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        return

    if data == "myplan":
        user = get_user(user_id)
        active_count = get_active_alerts_count(user_id)
        if user and user[2] == 1:
            expiry = user[3]
            if expiry:
                days_left = (datetime.fromisoformat(expiry) - datetime.now()).days
                await query.edit_message_text(
                    f"🌟 *Your Plan: Premium*\n\n📊 Active alerts: {active_count} / unlimited\n📅 Expires in: {days_left} days\n💎 You have full access!",
                    parse_mode="Markdown", reply_markup=get_main_menu())
            else:
                await query.edit_message_text(
                    f"🌟 *Your Plan: Premium*\n\n📊 Active alerts: {active_count} / unlimited\n💎 You have full access!",
                    parse_mode="Markdown", reply_markup=get_main_menu())
        else:
            await query.edit_message_text(
                f"📊 *Your Plan: Free*\n\n📈 Active alerts: {active_count} / {MAX_FREE_ALERTS}\n\n💰 Upgrade to Premium ($5/month) for unlimited alerts!\n📱 Contact: @{SUPPORT_USERNAME}",
                parse_mode="Markdown", reply_markup=get_main_menu())
        return

    if data == "prices":
        msg = "*💰 Live Prices:*\n\n*₿ Crypto:*\n"
        for coin in ['BTC', 'ETH', 'SOL']:
            price = await get_price_with_fallback('crypto', coin)
            msg += f"• *{coin}:* ${price:,.2f}\n" if price else f"• *{coin}:* ⚠️\n"
        msg += "\n*💱 Forex:*\n"
        for fx in ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD']:
            price = await get_price_with_fallback('forex', fx)
            if price:
                if fx == 'USDJPY':
                    msg += f"• *{fx}:* {price:.3f}\n"
                elif fx == 'XAUUSD':
                    msg += f"• *{fx}:* ${price:,.2f}\n"
                else:
                    msg += f"• *{fx}:* {price:.5f}\n"
            else:
                msg += f"• {fx}: ⚠️\n"
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_main_menu())
        return

    if data == "my_alerts":
        alerts = get_user_alerts(user_id)
        if not alerts:
            await query.edit_message_text("📋 No active alerts.", reply_markup=get_main_menu())
            return
        msg = "*📋 Your Alerts:*\n\n"
        for alert in alerts:
            alert_id, asset_type, symbol, price, direction = alert
            dir_text = "🔺 Above" if direction == "above" else "🔻 Below"
            emoji = "₿" if asset_type == "crypto" else "💱"
            msg += f"• {emoji} {symbol} {dir_text} ${price:,.2f}\n"
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_main_menu())
        return

    if data == "add_alert":
        context.user_data.clear()
        await query.edit_message_text("➕ *Add New Alert*\n\nChoose asset type:", parse_mode="Markdown", reply_markup=get_asset_type_menu())
        return

    if data == "back_to_asset":
        await query.edit_message_text("Choose asset type:", reply_markup=get_asset_type_menu())
        return

    if data == "asset_crypto":
        context.user_data['asset_type'] = 'crypto'
        await query.edit_message_text("Choose crypto symbol:", reply_markup=get_crypto_menu())
        return

    if data == "asset_forex":
        context.user_data['asset_type'] = 'forex'
        await query.edit_message_text("Choose forex pair:", reply_markup=get_forex_menu())
        return

    if data.startswith("crypto_"):
        symbol = data.split("_")[1]
        context.user_data['symbol'] = symbol
        context.user_data['step'] = 'waiting_price'
        await query.edit_message_text(f"✅ Selected: {symbol}\n\n📝 Send target price (e.g., 50000):", reply_markup=get_cancel_menu())
        return

    if data.startswith("forex_"):
        symbol = data.split("_")[1]
        context.user_data['symbol'] = symbol
        context.user_data['step'] = 'waiting_price'
        await query.edit_message_text(f"✅ Selected: {symbol}\n\n📝 Send target price (e.g., 1.1050):", reply_markup=get_cancel_menu())
        return

    if data == "custom_crypto":
        context.user_data['asset_type'] = 'crypto'
        context.user_data['step'] = 'waiting_custom_symbol'
        await query.edit_message_text("✏️ Enter custom crypto symbol (e.g., LTC, MATIC):", reply_markup=get_cancel_menu())
        return

    if data == "custom_forex":
        context.user_data['asset_type'] = 'forex'
        context.user_data['step'] = 'waiting_custom_symbol'
        await query.edit_message_text("✏️ Enter custom forex pair (e.g., EURGBP):", reply_markup=get_cancel_menu())
        return

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip().upper()

    if 'step' not in context.user_data:
        await update.message.reply_text("🌟 Use the buttons.", reply_markup=get_main_menu())
        return

    step = context.user_data['step']

    if step == 'waiting_custom_symbol':
        context.user_data['symbol'] = text
        context.user_data['step'] = 'waiting_price'
        await update.message.reply_text(f"✅ Symbol: {text}\n\n📝 Send target price:", reply_markup=get_cancel_menu())
        return

    if step == 'waiting_price':
        print(f"[DEBUG] User entered: {text}")
        try:
            price = float(text.replace(',', '.'))
            print(f"[DEBUG] Successfully converted to: {price}")
            asset_type = context.user_data.get('asset_type')
            symbol = context.user_data.get('symbol')
            user = get_user(user_id)
            if not user or user[2] == 0:
                active_count = get_active_alerts_count(user_id)
                if active_count >= MAX_FREE_ALERTS:
                    await update.message.reply_text(
                        f"⚠️ *Free limit reached ({MAX_FREE_ALERTS} alerts)!*\n\n"
                        f"Upgrade to Premium ($5/month) for unlimited alerts.\n"
                        f"📱 Contact: @{SUPPORT_USERNAME}",
                        parse_mode="Markdown", reply_markup=get_main_menu())
                    return
            
            save_alert(user_id, asset_type, symbol, price, 'above')
            await update.message.reply_text(
                f"✅ *Alert added!*\n\n• {symbol}\n• Target: ${price:,.2f}\n• Direction: 🔺 Above",
                parse_mode="Markdown", reply_markup=get_main_menu())
            context.user_data.clear()
        except Exception as e:
            print(f"[DEBUG] Conversion failed for '{text}': {e}")
            await update.message.reply_text("⚠️ Send a valid number (e.g., 1.1050).", reply_markup=get_cancel_menu())
        return

async def check_expired_subscriptions(app):
    while True:
        try:
            conn = sqlite3.connect('alerts.db')
            c = conn.cursor()
            now = datetime.now()
            three_days_later = now + timedelta(days=3)
            
            c.execute('''
                SELECT user_id, username, premium_until FROM users 
                WHERE is_premium = 1 AND premium_until IS NOT NULL
            ''')
            users = c.fetchall()
            conn.close()
            
            for user in users:
                user_id, username, premium_until = user
                premium_until = datetime.fromisoformat(premium_until)
                
                if premium_until < now:
                    downgrade_user(user_id)
                    try:
                        await app.bot.send_message(
                            chat_id=user_id,
                            text=f"⚠️ *Your Premium subscription has expired!*\n\n"
                                 f"Your account has been downgraded to Free.\n"
                                 f"To renew, please contact: @{SUPPORT_USERNAME}",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
                
                elif premium_until <= three_days_later:
                    days_left = (premium_until - now).days
                    try:
                        await app.bot.send_message(
                            chat_id=user_id,
                            text=f"🔔 *Reminder: Your Premium subscription expires in {days_left} days!*\n\n"
                                 f"Please contact @{SUPPORT_USERNAME} to renew and avoid interruption.",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
            
            await asyncio.sleep(86400)
        except Exception as e:
            print(f"⚠️ Error checking subscriptions: {e}")
            await asyncio.sleep(86400)

async def check_prices(app):
    while True:
        try:
            conn = sqlite3.connect('alerts.db')
            c = conn.cursor()
            c.execute('SELECT id, user_id, asset_type, symbol, target_price, direction FROM alerts WHERE is_active = 1')
            alerts = c.fetchall()
            conn.close()
            
            for alert in alerts:
                alert_id, user_id, asset_type, symbol, target, direction = alert
                current = await get_price_with_fallback(asset_type, symbol)
                
                if current:
                    triggered = (direction == 'above' and current >= target) or (direction == 'below' and current <= target)
                    if triggered:
                        emoji = "₿" if asset_type == "crypto" else "💱"
                        await app.bot.send_message(
                            chat_id=user_id,
                            text=f"🔔 *Price Alert!*\n\n{emoji} {symbol}\n• Target: ${target:,.2f}\n• Current: ${current:,.2f}",
                            parse_mode="Markdown")
                        deactivate_alert(alert_id)
            await asyncio.sleep(30)
        except Exception as e:
            print(f"⚠️ Error checking prices: {e}")
            await asyncio.sleep(60)

# ========== Run Bot with Auto-Restart ==========
app = None

async def run_bot():
    global app
    while True:
        try:
            app = Application.builder().token(TELEGRAM_TOKEN).build()
            app.add_handler(CommandHandler("start", start))
            app.add_handler(CallbackQueryHandler(button_handler))
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
            
            # Run background tasks
            asyncio.create_task(check_prices(app))
            asyncio.create_task(check_expired_subscriptions(app))
            
            print("✅ BRIDGES Bot is running...")
            print("🌐 Dashboard: http://localhost:8080")
            
            await app.initialize()
            await app.start()
            await app.updater.start_polling()
            
            # Keep running until interrupted
            while True:
                await asyncio.sleep(1)
                
        except Exception as e:
            print(f"❌ Bot crashed: {e}")
            print("🔄 Restarting in 10 seconds...")
            await asyncio.sleep(10)
        finally:
            if app:
                try:
                    await app.stop()
                except:
                    pass

def signal_handler(sig, frame):
    print("\n🛑 Shutting down gracefully...")
    sys.exit(0)

def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    init_db()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_bot())
    except KeyboardInterrupt:
        print("\n✅ Bot stopped by user")
    finally:
        loop.close()

if __name__ == "__main__":
    main()