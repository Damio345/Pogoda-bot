import asyncio
import logging
import json
import os
import urllib.parse
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiohttp import ClientSession, web
from apscheduler.schedulers.asyncio import AsyncIOScheduler

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("ОШИБКА: Переменная BOT_TOKEN не найдена в окружении!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

USERS_FILE = "user_settings.json"

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_users(data):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Failed to save users: {e}")

def clean_text(text):
    """Удаляет спецсимволы Markdown, чтобы Telegram не выдавал ошибку"""
    if not text:
        return ""
    return str(text).replace("_", "\\_").replace("*", "\\*").replace("`", "\\`").replace("[", "\\[")

def get_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Сегодня 📅", callback_data="period_1"),
            InlineKeyboardButton(text="На 3 дня 🗓", callback_data="period_3"),
            InlineKeyboardButton(text="На неделю 📊", callback_data="period_7")
        ]
    ])

async def fetch_weather(place_name, days=1):
    # Кодируем название города для безопасной передачи в URL
    encoded_place = urllib.parse.quote(place_name)
    url = f"https://wttr.in/{encoded_place}?format=j1&lang=ru"
    
    try:
        async with ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    return f"⚠️ Не удалось найти погоду для '{clean_text(place_name)}'."
                data = await resp.json()

        curr = data.get("current_condition", [{}])[0]
        weather_days = data.get("weather", [])
        area = data.get("nearest_area", [{}])[0]
        
        city = area.get("areaName", [{}])[0].get("value", place_name)
        country = area.get("country", [{}])[0].get("value", "")
        display_name = clean_text(f"{city}, {country}")

        if days == 1:
            today = weather_days[0] if weather_days else {}
            astronomy = today.get("astronomy", [{}])[0] if today.get("astronomy") else {}
            desc = curr.get("lang_ru", [{}])[0].get("value", curr.get("weatherDesc", [{}])[0].get("value", ""))

            return (
                f"📍 **Место:** {display_name}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🌡 **Температура:** {curr.get('temp_C')}°C (ощущается как {curr.get('FeelsLikeC')}°C)\n"
                f"📊 **Мин / Макс сегодня:** {today.get('mintempC')}°C ... {today.get('maxtempC')}°C\n"
                f"☁️ **Состояние:** {clean_text(desc)}\n"
                f"💧 **Влажность:** {curr.get('humidity')}%\n"
                f"💨 **Ветер:** {curr.get('windspeedKmph')} км/ч\n"
                f"⏲ **Давление:** {round(float(curr.get('pressure', 0)) * 0.750063)} мм рт. ст.\n"
                f"☀️ **УФ-Индекс:** {curr.get('uvIndex')}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🌅 **Восход:** {astronomy.get('sunrise', '--:--')} | 🌇 **Закат:** {astronomy.get('sunset', '--:--')}"
            )

        text = f"📍 **Прогноз на {days} дн. ({display_name}):**\n"
        for day_data in weather_days[:days]:
            date_str = day_data.get("date")
            astronomy = day_data.get("astronomy", [{}])[0] if day_data.get("astronomy") else {}
            hourly = day_data.get("hourly", [])
            noon_desc = hourly[4].get("lang_ru", [{}])[0].get("value", "") if len(hourly) > 4 else ""

            text += (
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"📅 **Дата:** {date_str}\n"
                f"☁️ **Состояние:** {clean_text(noon_desc)}\n"
                f"🌡 **Температура:** от {day_data.get('mintempC')}°C до {day_data.get('maxtempC')}°C\n"
                f"☀️ **УФ-индекс:** {day_data.get('uvIndex')}\n"
                f"🌅 **Восход:** {astronomy.get('sunrise', '--:--')} | 🌇 **Закат:** {astronomy.get('sunset', '--:--')}\n"
            )
        return text

    except Exception as e:
        logging.error(f"Fetch weather error: {e}")
        return "⚠️ Ошибка при получении погоды."

async def send_daily_weather():
    users = load_users()
    for user_id, user_info in users.items():
        if user_info.get("subscribed"):
            place_name = user_info.get("place")
            if place_name:
                try:
                    report = await fetch_weather(place_name, days=1)
                    await bot.send_message(
                        chat_id=int(user_id),
                        text=f"☀️ **Ежедневный утренний отчет!**\n\n{report}",
                        parse_mode="Markdown",
                        reply_markup=get_keyboard()
                    )
                except Exception as e:
                    logging.error(f"Failed send daily weather to {user_id}: {e}")

@dp.message(CommandStart())
async def start_cmd(message: Message):
    await message.answer("👋 Напиши название населенного пункта.\nЯ запомню его и буду присылать полные отчеты каждую утреннюю рассылку!")

@dp.message()
async def search_place(message: Message):
    place_name = message.text.strip()
    users = load_users()
    users[str(message.from_user.id)] = {"place": place_name, "subscribed": True}
    save_users(users)

    report = await fetch_weather(place_name, days=1)
    await message.answer(f"✅ Локация сохранена!\n\n{report}", parse_mode="Markdown", reply_markup=get_keyboard())

@dp.callback_query(lambda c: c.data and c.data.startswith('period_'))
async def process_period_choice(callback: CallbackQuery):
    await callback.answer("Загрузка...")
    try:
        days = int(callback.data.split('_')[1])
        user_id = str(callback.from_user.id)
        users = load_users()

        if user_id in users:
            place_name = users[user_id]['place']
            report = await fetch_weather(place_name, days=days)
            await callback.message.edit_text(report, parse_mode="Markdown", reply_markup=get_keyboard())
        else:
            await callback.message.answer("Сначала напишите название города или деревни!")
    except Exception as e:
        logging.error(f"Period choice error: {e}")

async def handle(request):
    return web.Response(text="Bot is running!")

async def main():
    logging.basicConfig(level=logging.INFO)

    scheduler = AsyncIOScheduler(timezone="Asia/Yekaterinburg")
    scheduler.add_job(send_daily_weather, 'cron', hour=9, minute=0)
    scheduler.start()

    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
