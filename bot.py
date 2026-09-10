import asyncio
import logging
import json
import os
import urllib.parse
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
TEMP_PLACES = {}  # Временное хранение вариантов поиска для обхода лимита 64 байт Telegram

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

def get_period_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Сегодня 📅", callback_data="period_1"),
            InlineKeyboardButton(text="На 3 дня 🗓", callback_data="period_3"),
            InlineKeyboardButton(text="На неделю 📊", callback_data="period_7")
        ]
    ])

async def search_places(query):
    """Ищет варианты населенных пунктов через Open-Meteo Geocoding"""
    encoded = urllib.parse.quote(query)
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded}&count=5&language=ru&format=json"
    
    try:
        async with ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    results = data.get("results", [])
                    places = []
                    for idx, item in enumerate(results):
                        name = item.get("name", "")
                        admin = item.get("admin1", "")
                        country = item.get("country", "")
                        
                        full_name = name
                        if admin and admin != name:
                            full_name += f", {admin}"
                        if country:
                            full_name += f" ({country})"
                            
                        lat, lon = item.get("latitude"), item.get("longitude")
                        places.append({"id": str(idx), "name": full_name, "query": f"{lat},{lon}"})
                    return places
    except Exception as e:
        logging.error(f"Geocoding error: {e}")
    return []

async def fetch_weather(query, days=1):
    encoded = urllib.parse.quote(query)
    url = f"https://wttr.in/{encoded}?format=j1&lang=ru"
    
    try:
        async with ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    return f"⚠️ Не удалось найти погоду."
                data = await resp.json(content_type=None)

        curr = data.get("current_condition", [{}])[0]
        weather_days = data.get("weather", [])
        area = data.get("nearest_area", [{}])[0]
        
        city = area.get("areaName", [{}])[0].get("value", query)
        region = area.get("region", [{}])[0].get("value", "")
        country = area.get("country", [{}])[0].get("value", "")
        
        display_name = city
        if region and region != city:
            display_name += f", {region}"
        if country:
            display_name += f" ({country})"

        if days == 1:
            today = weather_days[0] if weather_days else {}
            astronomy = today.get("astronomy", [{}])[0] if today.get("astronomy") else {}
            desc = curr.get("lang_ru", [{}])[0].get("value", curr.get("weatherDesc", [{}])[0].get("value", ""))

            return (
                f"📍 Место: {display_name}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🌡 Температура: {curr.get('temp_C')}°C (ощущается как {curr.get('FeelsLikeC')}°C)\n"
                f"📊 Мин / Макс сегодня: {today.get('mintempC')}°C ... {today.get('maxtempC')}°C\n"
                f"☁️ Состояние: {desc}\n"
                f"💧 Влажность: {curr.get('humidity')}%\n"
                f"💨 Ветер: {curr.get('windspeedKmph')} км/ч\n"
                f"⏲ Давление: {round(float(curr.get('pressure', 0)) * 0.750063)} мм рт. ст.\n"
                f"☀️ УФ-Индекс: {curr.get('uvIndex')}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🌅 Восход: {astronomy.get('sunrise', '--:--')} | 🌇 Закат: {astronomy.get('sunset', '--:--')}"
            )

        text = f"📍 Прогноз на {days} дн. ({display_name}):\n"
        for day_data in weather_days[:days]:
            date_str = day_data.get("date")
            astronomy = day_data.get("astronomy", [{}])[0] if day_data.get("astronomy") else {}
            hourly = day_data.get("hourly", [])
            noon_desc = hourly[4].get("lang_ru", [{}])[0].get("value", "") if len(hourly) > 4 else ""

            text += (
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"📅 Дата: {date_str}\n"
                f"☁️ Состояние: {noon_desc}\n"
                f"🌡 Температура: от {day_data.get('mintempC')}°C до {day_data.get('maxtempC')}°C\n"
                f"☀️ УФ-индекс: {day_data.get('uvIndex')}\n"
                f"🌅 Восход: {astronomy.get('sunrise', '--:--')} | 🌇 Закат: {astronomy.get('sunset', '--:--')}\n"
            )
        return text

    except Exception as e:
        logging.error(f"Fetch weather error: {e}")
        return "⚠️ Ошибка при получении погоды."

async def send_daily_weather():
    users = load_users()
    for user_id, user_info in users.items():
        if user_info.get("subscribed"):
            place_query = user_info.get("place")
            if place_query:
                try:
                    report = await fetch_weather(place_query, days=1)
                    await bot.send_message(
                        chat_id=int(user_id),
                        text=f"☀️ Ежедневный утренний отчет!\n\n{report}",
                        reply_markup=get_period_keyboard()
                    )
                except Exception as e:
                    logging.error(f"Failed send daily weather to {user_id}: {e}")

@dp.message(CommandStart())
async def start_cmd(message: Message):
    await message.answer("👋 Напиши название населенного пункта, и я помогу выбрать точный вариант!")

@dp.message()
async def search_place_handler(message: Message):
    user_id = str(message.from_user.id)
    query = message.text.strip()
    places = await search_places(query)

    if not places:
        users = load_users()
        users[user_id] = {"place": query, "subscribed": True}
        save_users(users)
        report = await fetch_weather(query, days=1)
        await message.answer(f"✅ Локация сохранена!\n\n{report}", reply_markup=get_period_keyboard())
        return

    if len(places) == 1:
        p = places[0]
        users = load_users()
        users[user_id] = {"place": p["query"], "subscribed": True}
        save_users(users)
        report = await fetch_weather(p["query"], days=1)
        await message.answer(f"✅ Сохранено: {p['name']}\n\n{report}", reply_markup=get_period_keyboard())
    else:
        # Сохраняем варианты в словаре TEMP_PLACES для пользователя
        TEMP_PLACES[user_id] = {p["id"]: p for p in places}
        buttons = []
        for p in places:
            cb_data = f"loc|{p['id']}"
            buttons.append([InlineKeyboardButton(text=p['name'], callback_data=cb_data)])
            
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer("🔍 Найдено несколько вариантов. Выберите ваш населенный пункт:", reply_markup=kb)

@dp.callback_query(lambda c: c.data and c.data.startswith('loc|'))
async def process_select_location(callback: CallbackQuery):
    await callback.answer("Сохраняем...")
    user_id = str(callback.from_user.id)
    place_id = callback.data.split('|')[1]
    
    user_temp = TEMP_PLACES.get(user_id, {})
    selected_place = user_temp.get(place_id)

    if selected_place:
        loc_query = selected_place["query"]
        users = load_users()
        users[user_id] = {"place": loc_query, "subscribed": True}
        save_users(users)

        report = await fetch_weather(loc_query, days=1)
        await callback.message.edit_text(f"✅ Сохранено: {selected_place['name']}\n\n{report}", reply_markup=get_period_keyboard())
    else:
        await callback.message.answer("Сессия выбора истекла. Напишите название города еще раз!")

@dp.callback_query(lambda c: c.data and c.data.startswith('period_'))
async def process_period_choice(callback: CallbackQuery):
    await callback.answer("Загрузка...")
    try:
        days = int(callback.data.split('_')[1])
        user_id = str(callback.from_user.id)
        users = load_users()

        if user_id in users:
            place_query = users[user_id]['place']
            report = await fetch_weather(place_query, days=days)
            await callback.message.edit_text(report, reply_markup=get_period_keyboard())
        else:
            await callback.message.answer("Сначала напишите название города!")
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
