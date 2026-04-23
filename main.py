import os
import sqlite3
import asyncio
from datetime import datetime, timedelta
from statistics import median
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import aiohttp
from flask import Flask, render_template_string, request, redirect, url_for
from threading import Thread
import signal
import sys

# ========== Config from env (secure by default) ==========
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
FCSAPI_KEY = os.getenv("FCSAPI_KEY", "")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "iyadbakri")
SUPPORT_PHONE = os.getenv("SUPPORT_PHONE", "+79522677714")
MAX_FREE_ALERTS = int(os.getenv("MAX_FREE_ALERTS", "3"))
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8080"))

CRYPTO_SYMBOLS = ['BTC', 'ETH', 'BNB', 'SOL', 'XRP', 'DOGE', 'ADA', 'LTC', 'TRX', 'DOT']
FOREX_SYMBOLS = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'NZDUSD', 'USDCHF', 'EURJPY', 'GBPJPY', 'XAUUSD']

CRYPTO_IDS = {
    'BTC': 'bitcoin', 'ETH': 'ethereum', 'BNB': 'binancecoin', 'SOL': 'solana', 'XRP': 'ripple',
    'DOGE': 'dogecoin', 'ADA': 'cardano', 'LTC': 'litecoin', 'TRX': 'tron', 'DOT': 'polkadot'
}

SUPPORTED_LANGS = ["en", "ru", "ar"]

I18N = {
    "en": {
        "language_name": "English",
        "app_title": "🚀 *BRIDGES - Crypto & Forex Alert Bot*",
        "start_body": "Monitor prices and receive instant alerts!\n\n• Free plan: {max_alerts} active alerts\n• Premium: Unlimited alerts ($5/month)\n\nChoose an option:",
        "btn_add_alert": "➕ Add Alert",
        "btn_my_alerts": "📋 My Alerts",
        "btn_prices": "💰 Prices",
        "btn_my_plan": "⭐ My Plan",
        "btn_support": "📞 Support",
        "btn_language": "🌍 Language",
        "cancelled": "❌ Cancelled.",
        "select_asset": "Choose asset type:",
        "add_alert_title": "➕ *Add New Alert*\n\nChoose asset type:",
        "choose_crypto": "Choose crypto symbol:",
        "choose_forex": "Choose forex pair:",
        "enter_custom_crypto": "✏️ Enter custom crypto symbol (e.g., LTC, MATIC):",
        "enter_custom_forex": "✏️ Enter custom forex pair (e.g., EURGBP):",
        "send_target_price": "📝 Send target price (e.g., {example}):",
        "symbol_saved": "✅ Symbol: {symbol}\n\n📝 Send target price:",
        "invalid_number": "⚠️ Send a valid number (e.g., 1.1050).",
        "use_buttons": "🌟 Use the buttons.",
        "no_alerts": "📋 No active alerts.",
        "my_alerts_title": "*📋 Your Alerts:*",
        "alert_line": "• {emoji} {symbol} {dir_text} ${price:,.2f}",
        "dir_above": "🔺 Above",
        "dir_below": "🔻 Below",
        "choose_direction": "Choose alert direction for {symbol}:",
        "dir_saved": "✅ Direction: {dir_text}\n\n📝 Send target price:",
        "free_limit": "⚠️ *Free limit reached ({max_alerts} alerts)!*\n\nUpgrade to Premium ($5/month) for unlimited alerts.\n📱 Contact: @{support}",
        "alert_added": "✅ *Alert added!*\n\n• {symbol}\n• Target: ${price:,.2f}\n• Direction: {dir_text}",
        "prices_header": "*💰 Live Prices:*\n\n*₿ Crypto:*",
        "prices_forex": "\n*💱 Forex:*",
        "support": "📞 *Support & Premium Upgrade*\n\n⭐ *Upgrade to Premium:*\n💰 *Price:* $5/month\n✨ *Benefits:* Unlimited alerts + Priority support\n\n📱 *Contact us to upgrade:*\n• WhatsApp: {phone}\n• Telegram: @{username}\n\n🕒 *Hours:* 9AM - 5PM (Friday off)\n\n_After payment, your account will be activated within minutes_",
        "plan_premium": "🌟 *Your Plan: Premium*\n\n📊 Active alerts: {count} / unlimited\n📅 Expires in: {days} days\n💎 You have full access!",
        "plan_premium_no_exp": "🌟 *Your Plan: Premium*\n\n📊 Active alerts: {count} / unlimited\n💎 You have full access!",
        "plan_free": "📊 *Your Plan: Free*\n\n📈 Active alerts: {count} / {max_alerts}\n\n💰 Upgrade to Premium ($5/month) for unlimited alerts!\n📱 Contact: @{support}",
        "lang_title": "🌍 *Choose language / Выберите язык / اختر اللغة*",
        "lang_changed": "✅ Language set to {lang_name}.",
        "price_unavailable": "⚠️",
        "sub_expired": "⚠️ *Your Premium subscription has expired!*\n\nYour account has been downgraded to Free.\nTo renew, please contact: @{support}",
        "sub_reminder": "🔔 *Reminder: Your Premium subscription expires in {days} days!*\n\nPlease contact @{support} to renew and avoid interruption.",
    },
    "ru": {
        "language_name": "Русский",
        "app_title": "🚀 *BRIDGES - Бот алертов Crypto & Forex*",
        "start_body": "Следите за ценами и получайте мгновенные алерты!\n\n• Бесплатно: {max_alerts} активных алерта\n• Premium: без ограничений ($5/месяц)\n\nВыберите действие:",
        "btn_add_alert": "➕ Добавить алерт",
        "btn_my_alerts": "📋 Мои алерты",
        "btn_prices": "💰 Цены",
        "btn_my_plan": "⭐ Мой тариф",
        "btn_support": "📞 Поддержка",
        "btn_language": "🌍 Язык",
        "cancelled": "❌ Отменено.",
        "select_asset": "Выберите тип актива:",
        "add_alert_title": "➕ *Новый алерт*\n\nВыберите тип актива:",
        "choose_crypto": "Выберите крипто-символ:",
        "choose_forex": "Выберите forex-пару:",
        "enter_custom_crypto": "✏️ Введите свой крипто-символ (например, LTC, MATIC):",
        "enter_custom_forex": "✏️ Введите свою forex-пару (например, EURGBP):",
        "send_target_price": "📝 Отправьте целевую цену (например, {example}):",
        "symbol_saved": "✅ Символ: {symbol}\n\n📝 Отправьте целевую цену:",
        "invalid_number": "⚠️ Введите корректное число (например, 1.1050).",
        "use_buttons": "🌟 Используйте кнопки.",
        "no_alerts": "📋 Нет активных алертов.",
        "my_alerts_title": "*📋 Ваши алерты:*",
        "alert_line": "• {emoji} {symbol} {dir_text} ${price:,.2f}",
        "dir_above": "🔺 Выше",
        "dir_below": "🔻 Ниже",
        "choose_direction": "Выберите направление для {symbol}:",
        "dir_saved": "✅ Направление: {dir_text}\n\n📝 Отправьте целевую цену:",
        "free_limit": "⚠️ *Лимит бесплатного тарифа ({max_alerts} алерта) достигнут!*\n\nПерейдите на Premium ($5/месяц) для безлимита.\n📱 Контакт: @{support}",
        "alert_added": "✅ *Алерт добавлен!*\n\n• {symbol}\n• Цель: ${price:,.2f}\n• Направление: {dir_text}",
        "prices_header": "*💰 Текущие цены:*\n\n*₿ Крипто:*",
        "prices_forex": "\n*💱 Форекс:*",
        "support": "📞 *Поддержка и Premium*\n\n⭐ *Переход на Premium:*\n💰 *Цена:* $5/месяц\n✨ *Плюсы:* безлимит алертов + приоритетная поддержка\n\n📱 *Связаться:*\n• WhatsApp: {phone}\n• Telegram: @{username}\n\n🕒 *Часы:* 9:00 - 17:00 (пятница выходной)\n\n_После оплаты аккаунт активируется в течение нескольких минут_",
        "plan_premium": "🌟 *Ваш тариф: Premium*\n\n📊 Активные алерты: {count} / безлимит\n📅 Осталось: {days} дн.\n💎 У вас полный доступ!",
        "plan_premium_no_exp": "🌟 *Ваш тариф: Premium*\n\n📊 Активные алерты: {count} / безлимит\n💎 У вас полный доступ!",
        "plan_free": "📊 *Ваш тариф: Free*\n\n📈 Активные алерты: {count} / {max_alerts}\n\n💰 Перейдите на Premium ($5/месяц) для безлимита!\n📱 Контакт: @{support}",
        "lang_title": "🌍 *Choose language / Выберите язык / اختر اللغة*",
        "lang_changed": "✅ Язык переключен: {lang_name}.",
        "price_unavailable": "⚠️",
        "sub_expired": "⚠️ *Ваша Premium-подписка истекла!*\n\nАккаунт переведен на Free.\nДля продления: @{support}",
        "sub_reminder": "🔔 *Напоминание: Premium истекает через {days} дн.!*\n\nСвяжитесь с @{support}, чтобы продлить подписку.",
    },
    "ar": {
        "language_name": "العربية",
        "app_title": "🚀 *BRIDGES - بوت تنبيهات الكريبتو والفوركس*",
        "start_body": "تابع الأسعار واحصل على تنبيهات فورية!\n\n• الخطة المجانية: {max_alerts} تنبيهات نشطة\n• Premium: تنبيهات غير محدودة (5$/شهرياً)\n\nاختر من القائمة:",
        "btn_add_alert": "➕ إضافة تنبيه",
        "btn_my_alerts": "📋 تنبيهاتي",
        "btn_prices": "💰 الأسعار",
        "btn_my_plan": "⭐ خطتي",
        "btn_support": "📞 الدعم",
        "btn_language": "🌍 اللغة",
        "cancelled": "❌ تم الإلغاء.",
        "select_asset": "اختر نوع الأصل:",
        "add_alert_title": "➕ *إضافة تنبيه جديد*\n\nاختر نوع الأصل:",
        "choose_crypto": "اختر رمز الكريبتو:",
        "choose_forex": "اختر زوج الفوركس:",
        "enter_custom_crypto": "✏️ أدخل رمز كريبتو مخصص (مثال: LTC, MATIC):",
        "enter_custom_forex": "✏️ أدخل زوج فوركس مخصص (مثال: EURGBP):",
        "send_target_price": "📝 أرسل السعر المستهدف (مثال: {example}):",
        "symbol_saved": "✅ الرمز: {symbol}\n\n📝 أرسل السعر المستهدف:",
        "invalid_number": "⚠️ أرسل رقماً صحيحاً (مثال: 1.1050).",
        "use_buttons": "🌟 استخدم الأزرار.",
        "no_alerts": "📋 لا توجد تنبيهات نشطة.",
        "my_alerts_title": "*📋 تنبيهاتك:*",
        "alert_line": "• {emoji} {symbol} {dir_text} ${price:,.2f}",
        "dir_above": "🔺 أعلى من",
        "dir_below": "🔻 أقل من",
        "choose_direction": "اختر اتجاه التنبيه لـ {symbol}:",
        "dir_saved": "✅ الاتجاه: {dir_text}\n\n📝 أرسل السعر المستهدف:",
        "free_limit": "⚠️ *تم الوصول لحد الخطة المجانية ({max_alerts} تنبيهات)!*\n\nاشترك Premium (5$/شهرياً) لتنبيهات غير محدودة.\n📱 التواصل: @{support}",
        "alert_added": "✅ *تمت إضافة التنبيه!*\n\n• {symbol}\n• الهدف: ${price:,.2f}\n• الاتجاه: {dir_text}",
        "prices_header": "*💰 الأسعار المباشرة:*\n\n*₿ العملات الرقمية:*",
        "prices_forex": "\n*💱 الفوركس:*",
        "support": "📞 *الدعم والاشتراك Premium*\n\n⭐ *الترقية إلى Premium:*\n💰 *السعر:* 5$/شهرياً\n✨ *المميزات:* تنبيهات غير محدودة + دعم أولوية\n\n📱 *تواصل معنا:*\n• واتساب: {phone}\n• تيليجرام: @{username}\n\n🕒 *الدوام:* 9 صباحاً - 5 مساءً (الجمعة عطلة)\n\n_بعد الدفع سيتم تفعيل الحساب خلال دقائق_",
        "plan_premium": "🌟 *خطتك: Premium*\n\n📊 التنبيهات النشطة: {count} / غير محدود\n📅 ينتهي خلال: {days} يوم\n💎 لديك وصول كامل!",
        "plan_premium_no_exp": "🌟 *خطتك: Premium*\n\n📊 التنبيهات النشطة: {count} / غير محدود\n💎 لديك وصول كامل!",
        "plan_free": "📊 *خطتك: Free*\n\n📈 التنبيهات النشطة: {count} / {max_alerts}\n\n💰 اشترك Premium (5$/شهرياً) لتنبيهات غير محدودة!\n📱 التواصل: @{support}",
        "lang_title": "🌍 *Choose language / Выберите язык / اختر اللغة*",
        "lang_changed": "✅ تم اختيار اللغة: {lang_name}.",
        "price_unavailable": "⚠️",
        "sub_expired": "⚠️ *انتهى اشتراك Premium!*\n\nتم تحويل حسابك إلى الخطة المجانية.\nللتجديد تواصل مع: @{support}",
        "sub_reminder": "🔔 *تذكير: ينتهي اشتراك Premium خلال {days} يوم!*\n\nتواصل مع @{support} للتجديد.",
    }
}


def tr(lang: str, key: str, **kwargs) -> str:
    text = I18N.get(lang, I18N["en"]).get(key, I18N["en"].get(key, key))
    return text.format(**kwargs) if kwargs else text


# ========== Database ==========
def init_db():
    conn = sqlite3.connect('alerts.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            language TEXT DEFAULT 'en',
            is_premium INTEGER DEFAULT 0,
            premium_until TIMESTAMP,
            created_at TIMESTAMP
        )
    ''')
    # Migration for old DBs
    c.execute("PRAGMA table_info(users)")
    cols = [row[1] for row in c.fetchall()]
    if 'language' not in cols:
        c.execute("ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'en'")

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
              (user_id, username, datetime.now().isoformat()))
    c.execute("UPDATE users SET username = COALESCE(?, username) WHERE user_id = ?", (username, user_id))
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = sqlite3.connect('alerts.db')
    c = conn.cursor()
    c.execute("SELECT user_id, username, language, is_premium, premium_until FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user


def get_user_lang(user_id):
    user = get_user(user_id)
    if user and user[2] in SUPPORTED_LANGS:
        return user[2]
    return "en"


def set_user_language(user_id, lang):
    if lang not in SUPPORTED_LANGS:
        return
    conn = sqlite3.connect('alerts.db')
    c = conn.cursor()
    c.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
    conn.commit()
    conn.close()


def upgrade_user(user_id, days=30):
    conn = sqlite3.connect('alerts.db')
    c = conn.cursor()
    premium_until = datetime.now() + timedelta(days=days)
    c.execute("UPDATE users SET is_premium = 1, premium_until = ? WHERE user_id = ?", (premium_until.isoformat(), user_id))
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
    ''', (user_id, asset_type, symbol, target_price, direction, datetime.now().isoformat()))
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
        SELECT u.user_id, u.username, u.language, u.is_premium, u.premium_until, u.created_at,
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
        if user[3] == 1 and user[4]:
            expiry = datetime.fromisoformat(user[4])
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
            'language': user[2] or 'en',
            'is_premium': user[3],
            'premium_until': user[4],
            'start_date': start_date.strftime('%Y-%m-%d') if start_date else None,
            'created_at': user[5],
            'alerts_count': user[6],
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
async def fetch_json(url, timeout=10):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    return await response.json()
    except Exception:
        return None
    return None


async def get_crypto_sources(symbol):
    sources = []

    coin_id = CRYPTO_IDS.get(symbol)
    if coin_id:
        data = await fetch_json(f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd")
        if data and data.get(coin_id, {}).get('usd'):
            sources.append(float(data[coin_id]['usd']))

    data = await fetch_json(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT")
    if data and data.get('price'):
        sources.append(float(data['price']))

    kraken_pair = f"{symbol}USD"
    data = await fetch_json(f"https://api.kraken.com/0/public/Ticker?pair={kraken_pair}")
    if data and data.get('result'):
        for _, values in data['result'].items():
            if 'c' in values and values['c']:
                sources.append(float(values['c'][0]))
                break

    data = await fetch_json(f"https://api.coinbase.com/v2/prices/{symbol}-USD/spot")
    if data and data.get('data', {}).get('amount'):
        sources.append(float(data['data']['amount']))

    return sources


async def get_crypto_price(symbol):
    prices = await get_crypto_sources(symbol)
    if not prices:
        return None
    stable_price = median(prices)
    print(f"✅ [CRYPTO-MEDIAN] {symbol} = {stable_price} from {len(prices)} source(s)")
    return stable_price


async def get_forex_sources(symbol):
    sources = []
    from_currency = symbol[:3]
    to_currency = symbol[3:]

    if FCSAPI_KEY:
        if symbol == 'XAUUSD':
            url = f"https://fcsapi.com/api-v3/commodity/latest?symbol={symbol}&type=commodity&access_key={FCSAPI_KEY}"
        else:
            url = f"https://fcsapi.com/api-v3/forex/latest?symbol={symbol}&access_key={FCSAPI_KEY}"
        data = await fetch_json(url)
        if data and data.get('status') and data.get('response'):
            try:
                sources.append(float(data['response'][0]['price']))
            except Exception:
                pass

    if symbol == 'XAUUSD':
        data = await fetch_json("https://api.coingecko.com/api/v3/simple/price?ids=tether-gold&vs_currencies=usd")
        if data and data.get('tether-gold', {}).get('usd'):
            sources.append(float(data['tether-gold']['usd']))
        return sources

    data = await fetch_json(f"https://api.exchangerate.host/convert?from={from_currency}&to={to_currency}")
    if data and data.get('result'):
        sources.append(float(data['result']))

    data = await fetch_json(f"https://api.frankfurter.app/latest?from={from_currency}&to={to_currency}")
    if data and data.get('rates', {}).get(to_currency):
        sources.append(float(data['rates'][to_currency]))

    data = await fetch_json(f"https://open.er-api.com/v6/latest/{from_currency}")
    if data and data.get('result') == 'success' and data.get('rates', {}).get(to_currency):
        sources.append(float(data['rates'][to_currency]))

    return sources


async def get_forex_price(symbol):
    prices = await get_forex_sources(symbol)
    if not prices:
        print(f"❌ All sources failed for {symbol}")
        return None
    stable_price = median(prices)
    print(f"✅ [FOREX-MEDIAN] {symbol} = {stable_price} from {len(prices)} source(s)")
    return stable_price


async def get_price_with_fallback(asset_type, symbol):
    if asset_type == 'crypto':
        return await get_crypto_price(symbol)
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
                    <th>Lang</th>
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
                    <td>{{ user.language }}</td>
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
    web_app.run(host='0.0.0.0', port=DASHBOARD_PORT, debug=False, use_reloader=False)


Thread(target=run_web_server, daemon=True).start()


# ========== Bot Menus ==========
def get_main_menu(lang="en"):
    keyboard = [
        [InlineKeyboardButton(tr(lang, "btn_add_alert"), callback_data="add_alert")],
        [InlineKeyboardButton(tr(lang, "btn_my_alerts"), callback_data="my_alerts")],
        [InlineKeyboardButton(tr(lang, "btn_prices"), callback_data="prices")],
        [InlineKeyboardButton(tr(lang, "btn_my_plan"), callback_data="myplan")],
        [InlineKeyboardButton(tr(lang, "btn_support"), callback_data="support")],
        [InlineKeyboardButton(tr(lang, "btn_language"), callback_data="change_language")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_language_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("English 🇬🇧", callback_data="lang_en")],
        [InlineKeyboardButton("Русский 🇷🇺", callback_data="lang_ru")],
        [InlineKeyboardButton("العربية 🇸🇦", callback_data="lang_ar")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_main")],
    ])


def get_asset_type_menu(lang="en"):
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


def get_direction_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔺 Above", callback_data="direction_above")],
        [InlineKeyboardButton("🔻 Below", callback_data="direction_below")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])


def get_cancel_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel")]])


# ========== Bot Handlers ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username)
    lang = get_user_lang(user.id)
    await update.message.reply_text(
        f"{tr(lang, 'app_title')}\n\n"
        f"{tr(lang, 'start_body', max_alerts=MAX_FREE_ALERTS)}",
        parse_mode="Markdown",
        reply_markup=get_main_menu(lang)
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    lang = get_user_lang(user_id)

    if data == "cancel":
        context.user_data.clear()
        await query.edit_message_text(tr(lang, "cancelled"), reply_markup=get_main_menu(lang))
        return

    if data == "back_main":
        await query.edit_message_text(tr(lang, "select_asset"), reply_markup=get_main_menu(lang))
        return

    if data == "change_language":
        await query.edit_message_text(tr(lang, "lang_title"), parse_mode="Markdown", reply_markup=get_language_menu())
        return

    if data.startswith("lang_"):
        selected = data.split("_", 1)[1]
        set_user_language(user_id, selected)
        lang = get_user_lang(user_id)
        await query.edit_message_text(
            tr(lang, "lang_changed", lang_name=tr(lang, "language_name")),
            reply_markup=get_main_menu(lang)
        )
        return

    if data == "support":
        await query.edit_message_text(
            tr(lang, "support", phone=SUPPORT_PHONE, username=SUPPORT_USERNAME),
            parse_mode="Markdown",
            reply_markup=get_main_menu(lang)
        )
        return

    if data == "myplan":
        user = get_user(user_id)
        active_count = get_active_alerts_count(user_id)
        if user and user[3] == 1:
            expiry = user[4]
            if expiry:
                days_left = (datetime.fromisoformat(expiry) - datetime.now()).days
                await query.edit_message_text(
                    tr(lang, "plan_premium", count=active_count, days=days_left),
                    parse_mode="Markdown", reply_markup=get_main_menu(lang))
            else:
                await query.edit_message_text(
                    tr(lang, "plan_premium_no_exp", count=active_count),
                    parse_mode="Markdown", reply_markup=get_main_menu(lang))
        else:
            await query.edit_message_text(
                tr(lang, "plan_free", count=active_count, max_alerts=MAX_FREE_ALERTS, support=SUPPORT_USERNAME),
                parse_mode="Markdown", reply_markup=get_main_menu(lang))
        return

    if data == "prices":
        msg = tr(lang, "prices_header") + "\n"
        for coin in ['BTC', 'ETH', 'SOL', 'BNB']:
            price = await get_price_with_fallback('crypto', coin)
            msg += f"• *{coin}:* ${price:,.2f}\n" if price else f"• *{coin}:* {tr(lang, 'price_unavailable')}\n"
        msg += tr(lang, "prices_forex") + "\n"
        for fx in ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'USDCHF']:
            price = await get_price_with_fallback('forex', fx)
            if price:
                if fx == 'USDJPY':
                    msg += f"• *{fx}:* {price:.3f}\n"
                elif fx == 'XAUUSD':
                    msg += f"• *{fx}:* ${price:,.2f}\n"
                else:
                    msg += f"• *{fx}:* {price:.5f}\n"
            else:
                msg += f"• {fx}: {tr(lang, 'price_unavailable')}\n"
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_main_menu(lang))
        return

    if data == "my_alerts":
        alerts = get_user_alerts(user_id)
        if not alerts:
            await query.edit_message_text(tr(lang, "no_alerts"), reply_markup=get_main_menu(lang))
            return
        msg = tr(lang, "my_alerts_title") + "\n\n"
        for alert in alerts:
            _, asset_type, symbol, price, direction = alert
            dir_text = tr(lang, "dir_above") if direction == "above" else tr(lang, "dir_below")
            emoji = "₿" if asset_type == "crypto" else "💱"
            msg += tr(lang, "alert_line", emoji=emoji, symbol=symbol, dir_text=dir_text, price=price) + "\n"
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_main_menu(lang))
        return

    if data == "add_alert":
        context.user_data.clear()
        await query.edit_message_text(tr(lang, "add_alert_title"), parse_mode="Markdown", reply_markup=get_asset_type_menu(lang))
        return

    if data == "back_to_asset":
        await query.edit_message_text(tr(lang, "select_asset"), reply_markup=get_asset_type_menu(lang))
        return

    if data == "asset_crypto":
        context.user_data['asset_type'] = 'crypto'
        await query.edit_message_text(tr(lang, "choose_crypto"), reply_markup=get_crypto_menu())
        return

    if data == "asset_forex":
        context.user_data['asset_type'] = 'forex'
        await query.edit_message_text(tr(lang, "choose_forex"), reply_markup=get_forex_menu())
        return

    if data.startswith("crypto_"):
        symbol = data.split("_")[1]
        context.user_data['symbol'] = symbol
        context.user_data['step'] = 'waiting_direction'
        await query.edit_message_text(tr(lang, "choose_direction", symbol=symbol), reply_markup=get_direction_menu())
        return

    if data.startswith("forex_"):
        symbol = data.split("_")[1]
        context.user_data['symbol'] = symbol
        context.user_data['step'] = 'waiting_direction'
        await query.edit_message_text(tr(lang, "choose_direction", symbol=symbol), reply_markup=get_direction_menu())
        return

    if data == "direction_above" or data == "direction_below":
        direction = data.split("_")[1]
        context.user_data['direction'] = direction
        context.user_data['step'] = 'waiting_price'
        dir_text = tr(lang, "dir_above") if direction == "above" else tr(lang, "dir_below")
        await query.edit_message_text(tr(lang, "dir_saved", dir_text=dir_text), reply_markup=get_cancel_menu())
        return

    if data == "custom_crypto":
        context.user_data['asset_type'] = 'crypto'
        context.user_data['step'] = 'waiting_custom_symbol'
        await query.edit_message_text(tr(lang, "enter_custom_crypto"), reply_markup=get_cancel_menu())
        return

    if data == "custom_forex":
        context.user_data['asset_type'] = 'forex'
        context.user_data['step'] = 'waiting_custom_symbol'
        await query.edit_message_text(tr(lang, "enter_custom_forex"), reply_markup=get_cancel_menu())
        return


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    text = update.message.text.strip().upper()

    if 'step' not in context.user_data:
        await update.message.reply_text(tr(lang, "use_buttons"), reply_markup=get_main_menu(lang))
        return

    step = context.user_data['step']

    if step == 'waiting_custom_symbol':
        context.user_data['symbol'] = text
        context.user_data['step'] = 'waiting_direction'
        await update.message.reply_text(tr(lang, "choose_direction", symbol=text), reply_markup=get_direction_menu())
        return

    if step == 'waiting_price':
        try:
            price = float(text.replace(',', '.'))
            asset_type = context.user_data.get('asset_type')
            symbol = context.user_data.get('symbol')
            direction = context.user_data.get('direction', 'above')
            user = get_user(user_id)
            if not user or user[3] == 0:
                active_count = get_active_alerts_count(user_id)
                if active_count >= MAX_FREE_ALERTS:
                    await update.message.reply_text(
                        tr(lang, "free_limit", max_alerts=MAX_FREE_ALERTS, support=SUPPORT_USERNAME),
                        parse_mode="Markdown", reply_markup=get_main_menu(lang))
                    return

            save_alert(user_id, asset_type, symbol, price, direction)
            dir_text = tr(lang, "dir_above") if direction == "above" else tr(lang, "dir_below")
            await update.message.reply_text(
                tr(lang, "alert_added", symbol=symbol, price=price, dir_text=dir_text),
                parse_mode="Markdown", reply_markup=get_main_menu(lang))
            context.user_data.clear()
        except Exception:
            await update.message.reply_text(tr(lang, "invalid_number"), reply_markup=get_cancel_menu())
        return


async def check_expired_subscriptions(app):
    while True:
        try:
            conn = sqlite3.connect('alerts.db')
            c = conn.cursor()
            now = datetime.now()
            three_days_later = now + timedelta(days=3)

            c.execute('''
                SELECT user_id, username, language, premium_until FROM users
                WHERE is_premium = 1 AND premium_until IS NOT NULL
            ''')
            users = c.fetchall()
            conn.close()

            for user in users:
                user_id, _, lang, premium_until = user
                lang = lang if lang in SUPPORTED_LANGS else "en"
                premium_until = datetime.fromisoformat(premium_until)

                if premium_until < now:
                    downgrade_user(user_id)
                    try:
                        await app.bot.send_message(
                            chat_id=user_id,
                            text=tr(lang, "sub_expired", support=SUPPORT_USERNAME),
                            parse_mode="Markdown"
                        )
                    except Exception:
                        pass

                elif premium_until <= three_days_later:
                    days_left = (premium_until - now).days
                    try:
                        await app.bot.send_message(
                            chat_id=user_id,
                            text=tr(lang, "sub_reminder", days=days_left, support=SUPPORT_USERNAME),
                            parse_mode="Markdown"
                        )
                    except Exception:
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
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "YOUR_BOT_TOKEN":
        raise RuntimeError("TELEGRAM_TOKEN is not set. Put it into .env or environment variables.")

    while True:
        try:
            app = Application.builder().token(TELEGRAM_TOKEN).build()
            app.add_handler(CommandHandler("start", start))
            app.add_handler(CallbackQueryHandler(button_handler))
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

            asyncio.create_task(check_prices(app))
            asyncio.create_task(check_expired_subscriptions(app))

            print("✅ BRIDGES Bot is running...")
            print(f"🌐 Dashboard: http://localhost:{DASHBOARD_PORT}")

            await app.initialize()
            await app.start()
            await app.updater.start_polling()

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
                except Exception:
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
