import asyncio
import logging
import json
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiohttp import web, ClientSession

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
        except Exception as e:
            logging.error(f"Error reading JSON: {e}")
            return {}
    return {}

def save_users(data):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Failed to save users: {e}")

def get_wind_direction(deg):
    try:
        dirs = ['Северный ⬆️', 'Северо-восточный ↗️', 'Восточный ➡️', 'Юго-восточный ↘️',
                'Южный ⬇️', 'Юго-западный ↙️', 'Западный ⬅️', 'Северо-западный ↖️']
        return dirs[int((float(deg) + 22.5) / 45) % 8]
    except Exception:
        return "Неизвестно 🌀"

def get_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Сегодня 📅", callback_data="period_1"),
            InlineKeyboardButton(text="На 3 дня 🗓", callback_data="period_3"),
            InlineKeyboardButton(text="На неделю 📊", callback_data="period_7")
        ]
    ])

async def fetch_weather(lat, lon, display_name, days=1):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": str(lat),
        "longitude": str(lon),
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,surface_pressure,wind_speed_10m,wind_direction_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min,sunrise,sunset,uv_index_max,precipitation_sum,wind_speed_10m_max,wind_direction_10m_dominant",
        "timezone": "auto"
    }
    
    try:
        async with ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status != 200:
                    return "⚠️ Ошибка сервера погоды. Попробуйте позже."
                data = await resp.json()

        curr = data.get("current", {})
        daily = data.get("daily", {})

        if days == 1:
            cond = WEATHER_CODES.get(curr.get("weather_code", 0), "Неизвестно")
            wind_dir = get_wind_direction(curr.get("wind_direction_10m", 0))
            
            sunrise_raw = daily.get("sunrise", [""])[0]
            sunset_raw = daily.get("sunset", [""])[0]
            sunrise = sunrise_raw.split("T")[1] if "T" in sunrise_raw else "--:--"
            sunset = sunset_raw.split("T")[1] if "T" in sunset_raw else "--:--"

            press = round(curr.get("surface_pressure", 0) * 0.750063)

            return (
                f"📍 **Место:** {display_name}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🌡 **Температура:** {round(curr.get('temperature_2m', 0))}°C (ощущается как {round(curr.get('apparent_temperature', 0))}°C)\n"
                f"📊 **Мин / Макс сегодня:** {round(daily.get('temperature_2m_min', [0])[0])}°C ... {round(daily.get('temperature_2m_max', [0])[0])}°C\n"
                f"☁️ **Состояние:** {cond}\n"
                f"💧 **Влажность:** {round(curr.get('relative_humidity_2m', 0))}%\n"
                f"💨 **Ветер:** {round(curr.get('wind_speed_10m', 0))} км/ч ({wind_dir})\n"
                f"⏲ **Давление:** {press} мм рт. ст.\n"
                f"☀️ **УФ-Индекс:** {round(daily.get('uv_index_max', [0])[0], 1)}\n"
                f"🌧 **Осадки:** {round(daily.get('precipitation_sum', [0])[0], 1)} мм\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🌅 **Восход:** {sunrise} | 🌇 **Закат:** {sunset}"
            )

        text = f"📍 **Подробный прогноз ({display_name}):**\n"
        times = daily.get("time", [])
        for i in range(min(days, len(times))):
            date_str = times[i]
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                day_name = DAYS_TRANSLATE.get(date_obj.strftime("%A"), "")
                formatted_date = date_obj.strftime("%d.%m")
            except Exception:
                day_name = ""
                formatted_date = date_str

            cond = WEATHER_CODES.get(daily.get("weather_code", [])[i], "Неизвестно")
            t_min = round(daily.get("temperature_2m_min", [])[i])
            t_max = round(daily.get("temperature_2m_max", [])[i])
            app_min = round(daily.get("apparent_temperature_min", [])[i])
            app_max = round(daily.get("apparent_temperature_max", [])[i])

            wind_speed = round(daily.get("wind_speed_10m_max", [])[i])
            wind_dir = get_wind_direction(daily.get("wind_direction_10m_dominant", [])[i])
            precip = round(daily.get("precipitation_sum", [])[i], 1)
            uv = round(daily.get("uv_index_max", [])[i], 1)

            sr = daily.get("sunrise", [])[i].split("T")[1] if "T" in daily.get("sunrise", [])[i] else "--:--"
            ss = daily.get("sunset", [])[i].split("T")[1] if "T" in daily.get("sunset", [])[i] else "--:--"

            text += (
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"📅 **{day_name} ({formatted_date})**\n"
                f"☁️ **Состояние:** {cond}\n"
                f"🌡 **Температура:** от {t_min}°C до {t_max}°C\n"
                f"🤔 **Ощущается как:** от {app_min}°C до {app_max}°C\n"
                f"💨 **Ветер макс.:** {wind_speed} км/ч ({wind_dir})\n"
                f"🌧 **Осадки:** {precip} мм\n"
                f"☀️ **УФ-индекс:** {uv}\n"
                f"🌅 **Восход:** {sr} | 🌇 **Закат:** {ss}\n"
            )
        return text

    except Exception as e:
        logging.error(f"Fetch weather error: {e}")
        return "⚠️ Произошла ошибка при получении погоды."

@dp.message(CommandStart())
async def start_cmd(message: Message):
    await message.answer("👋 Напиши название населенного пункта.\nЯ запомню его и буду присылать полные отчеты!")

@dp.message()
async def search_place(message: Message):
    place_name = message.text.strip()
    headers = {"User-Agent": "WeatherAppBot/2.0"}
    geo_url = f"https://nominatim.openstreetmap.org/search?q={place_name}&format=json&addressdetails=1&limit=3"

    try:
        async with ClientSession() as session:
            async with session.get(geo_url, headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    await message.answer("⚠️ Поиск мест временно недоступен.")
                    return
                geo_res = await resp.json()

        if not geo_res:
            await message.answer("❌ Ничего не найдено. Попробуй уточнить название.")
            return

        if len(geo_res) == 1:
            p = geo_res[0]
            users = load_users()
            users[str(message.from_user.id)] = {
                "lat": float(p['lat']), "lon": float(p['lon']),
                "name": p['display_name'], "subscribed": True
            }
            save_users(users)

            report = await fetch_weather(p['lat'], p['lon'], p['display_name'], days=1)
            await message.answer(f"✅ Локация сохранена!\n\n{report}", parse_mode="Markdown", reply_markup=get_keyboard())
            return

        buttons = []
        for item in geo_res:
            short_title = item['display_name'][:35] + "..."
            lat = round(float(item['lat']), 4)
            lon = round(float(item['lon']), 4)
            cb_data = f"geo:{lat}:{lon}"
            buttons.append([InlineKeyboardButton(text=short_title, callback_data=cb_data)])

        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer("🔎 Выбери точное место (я его запомню):", reply_markup=kb)

    except Exception as e:
        logging.error(f"Search place error: {e}")
        await message.answer("⚠️ Ошибка при поиске города.")

@dp.callback_query(lambda c: c.data and c.data.startswith('geo:'))
async def process_place_choice(callback: CallbackQuery):
    try:
        parts = callback.data.split(':')
        lat, lon = float(parts[1]), float(parts[2])
        user_id = str(callback.from_user.id)

        headers = {"User-Agent": "WeatherAppBot/2.0"}
        rev_url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"

        display_name = f"Локация ({lat}, {lon})"
        try:
            async with ClientSession() as session:
                async with session.get(rev_url, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        rev_res = await resp.json()
                        display_name = rev_res.get('display_name', display_name)
        except Exception as e:
            logging.error(f"Reverse geocoding error: {e}")

        users = load_users()
        users[user_id] = {
            "lat": lat, "lon": lon,
            "name": display_name, "subscribed": True
        }
        save_users(users)

        report = await fetch_weather(lat, lon, display_name, days=1)
        await callback.message.edit_text(f"✅ Локация сохранена!\n\n{report}", parse_mode="Markdown", reply_markup=get_keyboard())
    except Exception as e:
        logging.error(f"Callback place error: {e}")
        await callback.answer("Ошибка при сохранении.", show_alert=True)
    finally:
        await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith('period_'))
async def process_period_choice(callback: CallbackQuery):
    try:
        days = int(callback.data.split('_')[1])
        user_id = str(callback.from_user.id)
        users = load_users()

        if user_id in users:
            info = users[user_id]
            report = await fetch_weather(info['lat'], info['lon'], info['name'], days=days)
            await callback.message.edit_text(report, parse_mode="Markdown", reply_markup=get_keyboard())
        else:
            await callback.answer("Сначала напишите название вашей деревни или города!", show_alert=True)
    except Exception as e:
        logging.error(f"Period choice error: {e}")
    finally:
        await callback.answer()

async def handle(request):
    return web.Response(text="Bot is running!")

async def main():
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
