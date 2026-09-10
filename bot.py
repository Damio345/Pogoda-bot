import asyncio
import logging
import json
import os
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiohttp import ClientSession, web

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEATHER_KEY = os.getenv("WEATHER_KEY")

if not BOT_TOKEN:
    raise ValueError("ОШИБКА: Переменная BOT_TOKEN не найдена в окружении!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

USERS_FILE = "user_settings.json"

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
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Failed to save users: {e}")

def get_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Сегодня 📅", callback_data="period_1"),
            InlineKeyboardButton(text="На 3 дня 🗓", callback_data="period_3"),
            InlineKeyboardButton(text="На неделю 📊", callback_data="period_7")
        ]
    ])

async def fetch_weather(query, days=1):
    if not WEATHER_KEY:
        return "⚠️ Не задан WEATHER_KEY в настройках Render!"
        
    url = "https://api.weatherapi.com/v1/forecast.json"
    params = {
        "key": WEATHER_KEY,
        "q": query,
        "days": days,
        "lang": "ru"
    }
    
    try:
        async with ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status != 200:
                    return f"⚠️ Ошибка сервера погоды (Код: {resp.status})."
                data = await resp.json()

        loc = data.get("location", {})
        curr = data.get("current", {})
        forecast = data.get("forecast", {}).get("forecastday", [])

        display_name = f"{loc.get('name')}, {loc.get('region', '')} ({loc.get('country')})"

        if days == 1:
            today_f = forecast[0]['day'] if forecast else {}
            astro = forecast[0]['astro'] if forecast else {}

            return (
                f"📍 **Место:** {display_name}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🌡 **Температура:** {round(curr.get('temp_c', 0))}°C (ощущается как {round(curr.get('feelslike_c', 0))}°C)\n"
                f"📊 **Мин / Макс сегодня:** {round(today_f.get('mintemp_c', 0))}°C ... {round(today_f.get('maxtemp_c', 0))}°C\n"
                f"☁️ **Состояние:** {curr.get('condition', {}).get('text', '')}\n"
                f"💧 **Влажность:** {curr.get('humidity', 0)}%\n"
                f"💨 **Ветер:** {round(curr.get('wind_kph', 0))} км/ч\n"
                f"⏲ **Давление:** {round(curr.get('pressure_mb', 0) * 0.750063)} мм рт. ст.\n"
                f"☀️ **УФ-Индекс:** {curr.get('uv', 0)}\n"
                f"🌧 **Осадки:** {today_f.get('totalprecip_mm', 0)} мм\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"🌅 **Восход:** {astro.get('sunrise', '--:--')} | 🌇 **Закат:** {astro.get('sunset', '--:--')}"
            )

        text = f"📍 **Подробный прогноз ({display_name}):**\n"
        for day_data in forecast:
            date_str = day_data.get("date")
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                day_name = DAYS_TRANSLATE.get(date_obj.strftime("%A"), "")
                formatted_date = date_obj.strftime("%d.%m")
            except Exception:
                day_name = ""
                formatted_date = date_str

            day = day_data.get("day", {})
            astro = day_data.get("astro", {})

            text += (
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"📅 **{day_name} ({formatted_date})**\n"
                f"☁️ **Состояние:** {day.get('condition', {}).get('text', '')}\n"
                f"🌡 **Температура:** от {round(day.get('mintemp_c', 0))}°C до {round(day.get('maxtemp_c', 0))}°C\n"
                f"💨 **Ветер макс.:** {round(day.get('maxwind_kph', 0))} км/ч\n"
                f"🌧 **Осадки:** {day.get('totalprecip_mm', 0)} мм\n"
                f"☀️ **УФ-индекс:** {day.get('uv', 0)}\n"
                f"🌅 **Восход:** {astro.get('sunrise', '--:--')} | 🌇 **Закат:** {astro.get('sunset', '--:--')}\n"
            )
        return text

    except Exception as e:
        logging.error(f"Fetch weather error: {e}")
        return "⚠️ Ошибка при получении погоды."

@dp.message(CommandStart())
async def start_cmd(message: Message):
    await message.answer("👋 Напиши название населенного пункта.\nЯ запомню его и буду присылать полные отчеты!")

@dp.message()
async def search_place(message: Message):
    place_name = message.text.strip()
    if not WEATHER_KEY:
        await message.answer("⚠️ Не настроен WEATHER_KEY!")
        return

    geo_url = f"https://api.weatherapi.com/v1/search.json?key={WEATHER_KEY}&q={place_name}"

    try:
        async with ClientSession() as session:
            async with session.get(geo_url, timeout=10) as resp:
                if resp.status != 200:
                    await message.answer("⚠️ Ошибка поиска локаций.")
                    return
                results = await resp.json()

        if not results:
            await message.answer("❌ Ничего не найдено. Попробуй уточнить название.")
            return

        if len(results) == 1:
            p = results[0]
            query = f"{p['lat']},{p['lon']}"
            users = load_users()
            users[str(message.from_user.id)] = {"query": query, "subscribed": True}
            save_users(users)

            report = await fetch_weather(query, days=1)
            await message.answer(f"✅ Локация сохранена!\n\n{report}", parse_mode="Markdown", reply_markup=get_keyboard())
            return

        buttons = []
        for item in results[:5]:
            title = f"{item.get('name')} ({item.get('region')}, {item.get('country')})"[:35]
            cb_data = f"geo:{item['lat']}:{item['lon']}"
            buttons.append([InlineKeyboardButton(text=title, callback_data=cb_data)])

        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer("🔎 Выбери точное место (я его запомню):", reply_markup=kb)

    except Exception as e:
        logging.error(f"Search place error: {e}")
        await message.answer("⚠️ Ошибка при поиске города.")

@dp.callback_query(lambda c: c.data and c.data.startswith('geo:'))
async def process_place_choice(callback: CallbackQuery):
    await callback.answer("Загрузка...") # Мгновенное гашение загрузки на кнопке
    try:
        parts = callback.data.split(':')
        query = f"{parts[1]},{parts[2]}"
        user_id = str(callback.from_user.id)

        users = load_users()
        users[user_id] = {"query": query, "subscribed": True}
        save_users(users)

        report = await fetch_weather(query, days=1)
        await callback.message.edit_text(f"✅ Локация сохранена!\n\n{report}", parse_mode="Markdown", reply_markup=get_keyboard())
    except Exception as e:
        logging.error(f"Callback place error: {e}")

@dp.callback_query(lambda c: c.data and c.data.startswith('period_'))
async def process_period_choice(callback: CallbackQuery):
    await callback.answer("Обновляю...") # Мгновенное гашение загрузки на кнопке
    try:
        days = int(callback.data.split('_')[1])
        user_id = str(callback.from_user.id)
        users = load_users()

        if user_id in users:
            query = users[user_id]['query']
            report = await fetch_weather(query, days=days)
            await callback.message.edit_text(report, parse_mode="Markdown", reply_markup=get_keyboard())
        else:
            await callback.message.answer("Сначала напишите название вашей деревни или города!")
    except Exception as e:
        logging.error(f"Period choice error: {e}")

async def handle(request):
    return web.Response(text="Bot is running!")

async def main():
    logging.basicConfig(level=logging.INFO)

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
