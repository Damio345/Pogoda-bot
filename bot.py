import asyncio
import logging
import json
import os
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiohttp import web

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

USERS_FILE = "user_settings.json"

WEATHER_CODES = {
    0: "Ясно ☀️", 1: "Преимущественно ясно 🌤", 2: "Переменная облачность ⛅️", 3: "Пасмурно ☁️",
    45: "Туман 🌫", 48: "Отложение инея 🌫", 51: "Лёгкая морось 🌧", 53: "Умеренная морось 🌧",
    55: "Плотная морось 🌧", 61: "Небольшой дождь 🌧", 63: "Умеренный дождь 🌧", 65: "Сильный дождь 🌧",
    71: "Небольшой снег 🌨", 73: "Умеренный снег 🌨", 75: "Сильный снег 🌨", 80: "Ливень 🌧",
    81: "Сильный ливень 🌧", 82: "Ураганный ливень ⛈", 95: "Гроза 🌩"
}

DAYS_TRANSLATE = {
    'Monday': 'Понедельник', 'Tuesday': 'Вторник', 'Wednesday': 'Среда',
    'Thursday': 'Четверг', 'Friday': 'Пятница', 'Saturday': 'Суббота', 'Sunday': 'Воскресенье'
}

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_users(data):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_wind_direction(deg):
    dirs = ['Северный ⬆️', 'Северо-восточный ↗️', 'Восточный ➡️', 'Юго-восточный ↘️',
            'Южный ⬇️', 'Юго-западный ↙️', 'Западный ⬅️', 'Северо-западный ↖️']
    return dirs[int((deg + 22.5) / 45) % 8]

def get_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Сегодня 📅", callback_data="period_1"),
            InlineKeyboardButton(text="На 3 дня 🗓", callback_data="period_3"),
            InlineKeyboardButton(text="На неделю 📊", callback_data="period_7")
        ]
    ])

async def fetch_weather(session: aiohttp.ClientSession, lat, lon, display_name, days=1):
    w_url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,surface_pressure,wind_speed_10m,wind_direction_10m"
        f"&daily=weather_code,temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min,"
        f"sunrise,sunset,uv_index_max,precipitation_sum,wind_speed_10m_max,wind_direction_10m_dominant"
        f"&timezone=auto"
    )
    async with session.get(w_url) as resp:
        w_res = await resp.json()

    daily = w_res['daily']
    
    if days == 1:
        curr = w_res['current']
        condition = WEATHER_CODES.get(curr['weather_code'], "Неизвестно")
        wind_dir = get_wind_direction(curr['wind_direction_10m'])
        pressure_mmHg = round(curr['surface_pressure'] * 0.750063)
        sunrise = daily['sunrise'][0].split('T')[1]
        sunset = daily['sunset'][0].split('T')[1]

        return (
            f"📍 **Место:** {display_name}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🌡 **Температура:** {round(curr['temperature_2m'])}°C (ощущается как {round(curr['apparent_temperature'])}°C)\n"
            f"📊 **Мин / Макс сегодня:** {round(daily['temperature_2m_min'][0])}°C ... {round(daily['temperature_2m_max'][0])}°C\n"
            f"☁️ **Состояние:** {condition}\n"
            f"💧 **Влажность:** {curr['relative_humidity_2m']}%\n"
            f"💨 **Ветер:** {round(curr['wind_speed_10m'])} км/ч ({wind_dir})\n"
            f"⏲ **Давление:** {pressure_mmHg} мм рт. ст.\n"
            f"☀️ **УФ-Индекс:** {daily['uv_index_max'][0]}\n"
            f"🌧 **Осадки:** {daily['precipitation_sum'][0]} мм\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🌅 **Восход:** {sunrise} | 🌇 **Закат:** {sunset}"
        )
    
    text = f"📍 **Подробный прогноз ({display_name}):**\n"
    for i in range(days):
        date_obj = datetime.strptime(daily['time'][i], "%Y-%m-%d")
        day_name = DAYS_TRANSLATE.get(date_obj.strftime("%A"), "")
        date_str = date_obj.strftime("%d.%m")
        
        cond = WEATHER_CODES.get(daily['weather_code'][i], "Неизвестно")
        t_min = round(daily['temperature_2m_min'][i])
        t_max = round(daily['temperature_2m_max'][i])
        app_min = round(daily['apparent_temperature_min'][i])
        app_max = round(daily['apparent_temperature_max'][i])
        
        wind_speed = round(daily['wind_speed_10m_max'][i])
        wind_dir = get_wind_direction(daily['wind_direction_10m_dominant'][i])
        precip = daily['precipitation_sum'][i]
        uv = daily['uv_index_max'][i]
        sunrise = daily['sunrise'][i].split('T')[1]
        sunset = daily['sunset'][i].split('T')[1]

        text += (
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📅 **{day_name} ({date_str})**\n"
            f"☁️ **Состояние:** {cond}\n"
            f"🌡 **Температура:** от {t_min}°C до {t_max}°C\n"
            f"🤔 **Ощущается как:** от {app_min}°C до {app_max}°C\n"
            f"💨 **Ветер макс.:** {wind_speed} км/ч ({wind_dir})\n"
            f"🌧 **Осадки:** {precip} мм\n"
            f"☀️ **УФ-индекс:** {uv}\n"
            f"🌅 **Восход:** {sunrise} | 🌇 **Закат:** {sunset}\n"
        )
    return text

async def morning_scheduler(session: aiohttp.ClientSession):
    while True:
        now = datetime.now()
        if now.hour == 9 and now.minute == 0:
            users = load_users()
            for user_id, info in users.items():
                if info.get("subscribed"):
                    try:
                        report = await fetch_weather(session, info['lat'], info['lon'], info['name'], days=1)
                        await bot.send_message(
                            int(user_id), 
                            f"☕️ **Доброе утро! Прогноз погоды на сегодня:**\n\n{report}", 
                            parse_mode="Markdown",
                            reply_markup=get_keyboard()
                        )
                    except Exception:
                        pass
            await asyncio.sleep(60)
        await asyncio.sleep(30)

@dp.message(CommandStart())
async def start_cmd(message: Message):
    await message.answer(
        "👋 Напиши название населенного пункта.\n"
        "Я запомню его и буду присылать полные отчеты по дням!"
    )

@dp.message()
async def search_place(message: Message, session: aiohttp.ClientSession):
    place_name = message.text.strip()
    headers = {"User-Agent": "TelegramWeatherBot/1.0"}
    geo_url = f"https://nominatim.openstreetmap.org/search?q={place_name}&format=json&addressdetails=1&limit=3"
    
    try:
        async with session.get(geo_url, headers=headers) as resp:
            geo_res = await resp.json()

        if not geo_res:
            await message.answer("❌ Ничего не найдено. Попробуй уточнить название.")
            return

        if len(geo_res) == 1:
            p = geo_res[0]
            users = load_users()
            users[str(message.from_user.id)] = {
                "lat": p['lat'], "lon": p['lon'], 
                "name": p['display_name'], "subscribed": True
            }
            save_users(users)
            
            report = await fetch_weather(session, p['lat'], p['lon'], p['display_name'], days=1)
            await message.answer(f"✅ Локация сохранена!\n\n{report}", parse_mode="Markdown", reply_markup=get_keyboard())
            return

        buttons = []
        for item in geo_res:
            short_title = item['display_name'][:35] + "..."
            lat = round(float(item['lat']), 4)
            lon = round(float(item['lon']), 4)
            # Зашиваем координаты прямо в callback_data
            cb_data = f"geo:{lat}:{lon}"
            buttons.append([InlineKeyboardButton(text=short_title, callback_data=cb_data)])
        
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer("🔎 Выбери точное место (я его запомню):", reply_markup=kb)

    except Exception:
        await message.answer("⚠️ Ошибка поиска.")

@dp.callback_query(lambda c: c.data.startswith('geo:'))
async def process_place_choice(callback: CallbackQuery, session: aiohttp.ClientSession):
    _, lat, lon = callback.data.split(':')
    user_id = str(callback.from_user.id)
    
    headers = {"User-Agent": "TelegramWeatherBot/1.0"}
    rev_url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
    
    try:
        async with session.get(rev_url, headers=headers) as resp:
            rev_res = await resp.json()
        display_name = rev_res.get('display_name', 'Выбранная локация')
    except Exception:
        display_name = 'Выбранная локация'

    users = load_users()
    users[user_id] = {
        "lat": lat, "lon": lon, 
        "name": display_name, "subscribed": True
    }
    save_users(users)

    report = await fetch_weather(session, lat, lon, display_name, days=1)
    await callback.message.edit_text(f"✅ Локация сохранена!\n\n{report}", parse_mode="Markdown", reply_markup=get_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('period_'))
async def process_period_choice(callback: CallbackQuery, session: aiohttp.ClientSession):
    days = int(callback.data.split('_')[1])
    user_id = str(callback.from_user.id)
    users = load_users()
    
    if user_id in users:
        info = users[user_id]
        report = await fetch_weather(session, info['lat'], info['lon'], info['name'], days=days)
        await callback.message.edit_text(report, parse_mode="Markdown", reply_markup=get_keyboard())
    else:
        await callback.answer("Сначала напишите название вашей деревни или города!")
    await callback.answer()

async def handle(request):
    return web.Response(text="Bot is running!")

async def main():
    async with aiohttp.ClientSession() as session:
        dp["session"] = session
        asyncio.create_task(morning_scheduler(session))
        
        app = web.Application()
        app.router.add_get("/", handle)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.getenv("PORT", 8080))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        
        await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

