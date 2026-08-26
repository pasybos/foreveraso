import asyncio
import time
import sqlite3
import os
import random
import string
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, FSInputFile, LabeledPrice, PreCheckoutQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
import aiohttp

from config import BOT_TOKEN, ADMIN_IDS, FREE_HOURS, VPN_NAME, DB_PATH, CHANNEL_ID, PAYMENT_CONTACT, IMAGE_PATH, PUBLIC_URL, WEB_SERVER_HOST, WEB_SERVER_PORT, BOT_USERNAME
from database import init_db, get_user, add_or_update_user, delete_user, get_all_active_users, add_promocode, get_promocode, use_promocode, get_all_promocodes, get_setting, set_setting
from panel_api import PanelAPI
from utils import format_time_left, format_datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
panel = PanelAPI()

# ---------------------------------- тарифы ----------------------------------
TARIFFS = {
    "week": {"days": 7, "price_rub": "35 ₽", "price_stars": 25},
    "month": {"days": 30, "price_rub": "99 ₽", "price_stars": 50},
    "halfyear": {"days": 180, "price_rub": "549 ₽", "price_stars": 299},
    "year": {"days": 365, "price_rub": "999 ₽", "price_stars": 549},
    "forever": {"days": 3650, "price_rub": "2499 ₽", "price_stars": 1350},
}
TARIFF_NAMES = {
    "week": "Неделя",
    "month": "Месяц",
    "halfyear": "Полгода",
    "year": "Год",
    "forever": "Навсегда"
}

# ---------------------------------- состояния ----------------------------------
class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_days = State()
    waiting_for_ref_user_id = State()
    waiting_for_ref_days = State()
    waiting_for_promo_days = State()
    waiting_for_broadcast_text = State()
    waiting_for_broadcast_confirm = State()
    waiting_for_ref_settings = State()

class UserStates(StatesGroup):
    waiting_for_promo_code = State()

# ---------------------------------- КНОПКИ ----------------------------------
main_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📖 Инструкция", callback_data="instructions")],
    [InlineKeyboardButton(text="🚀 Получить подписку", callback_data="get_free")],
    [InlineKeyboardButton(text="💎 Купить подписку", callback_data="buy_menu")],
    [InlineKeyboardButton(text="🎁 Пробный период", callback_data="trial")]
])

bottom_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🎫 Промокод")],
        [KeyboardButton(text="📢 Канал"), KeyboardButton(text="❓ Поддержка")],
        [KeyboardButton(text="📜 Соглашение"), KeyboardButton(text="ℹ️ Политика")],
        [KeyboardButton(text="👥 Рефералы")]
    ],
    resize_keyboard=True
)

admin_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👥 Список пользователей")],
        [KeyboardButton(text="✅ Активировать подписку")],
        [KeyboardButton(text="✅ Активировать реферальную подписку")],
        [KeyboardButton(text="⚙️ Реферальные настройки")],
        [KeyboardButton(text="🎫 Создать промокод")],
        [KeyboardButton(text="📋 Список промокодов")],
        [KeyboardButton(text="📨 Сделать рассылку")],
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🔙 Выйти из админ-панели")]
    ],
    resize_keyboard=True
)

back_button = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
])

subscribe_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_ID.lstrip('@')}")],
    [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_sub")]
])

# ---------------------------------- проверка подписки на канал ----------------------------------
async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Ошибка проверки подписки для {user_id}: {e}")
        return False

# ---------------------------------- команда /start ----------------------------------
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    logger.info(f"Команда /start от {message.from_user.id}")
    args = message.text.split()
    if len(args) > 1:
        ref_data = args[1]
        if ref_data.startswith("ref_"):
            referrer_id_str = ref_data[4:]
            if referrer_id_str.isdigit():
                referrer_id = int(referrer_id_str)
                if referrer_id != message.from_user.id:
                    logger.info(f"Переход по реферальной ссылке от {referrer_id} для {message.from_user.id}")
                    await handle_referral(message.from_user.id, referrer_id)

    welcome_text = (
        f"✨ *Добро пожаловать в {VPN_NAME}!* ✨\n\n"
        "Быстрый, стабильный и приватный VPN в пару кликов.\n\n"
        "✅ Уже доступна бесплатная подписка — жмите «Получить подписку»\n"
        "🎁 Или заберите бесплатный «Пробный период»\n"
        "💎 Или купите подписку через «Купить подписку»\n"
        "📖 Если что-то непонятно — загляните в «Инструкция»\n\n"
        "Выберите раздел в меню ниже:"
    )

    if os.path.exists(IMAGE_PATH):
        try:
            await message.answer_photo(
                photo=FSInputFile(IMAGE_PATH),
                caption=welcome_text,
                parse_mode="Markdown",
                reply_markup=main_menu
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке фото: {e}")
            await message.answer(welcome_text, parse_mode="Markdown", reply_markup=main_menu)
    else:
        logger.warning(f"Файл {IMAGE_PATH} не найден.")
        await message.answer(welcome_text, parse_mode="Markdown", reply_markup=main_menu)

    await message.answer("👇 *Нижнее меню:*", parse_mode="Markdown", reply_markup=bottom_menu)

# ---------------------------------- команда /admin ----------------------------------
@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет прав администратора.")
        return
    await message.answer(
        f"👋 Добро пожаловать в админ-панель *{VPN_NAME}*!\n"
        "Используйте кнопки ниже для управления.",
        parse_mode="Markdown",
        reply_markup=admin_keyboard
    )

# ---------------------------------- СОЗДАНИЕ ПОДПИСКИ (общая функция) ----------------------------------
async def create_subscription(tg_id: int, days: int, tariff: str) -> str:
    """Создаёт клиента в панели и возвращает ссылку."""
    logger.info(f"Создание подписки для {tg_id} на {days} дней, тариф {tariff}")
    expire_ts = int(time.time()) + days * 86400
    email = f"{tariff}_{tg_id}_{int(time.time())}"
    client_id = await panel.create_client(email, expire_ts, total_gb=0, limit_ip=1 if tariff in ("free", "ref_bonus") else 3)
    link = await panel.get_client_link(client_id)
    add_or_update_user(tg_id, tariff, expire_ts, panel_client_id=client_id, current_link=link)
    logger.info(f"Подписка создана, ссылка: {link[:30]}...")
    return link

# ---------------------------------- РЕФЕРАЛЬНАЯ СИСТЕМА ----------------------------------
async def handle_referral(new_user_id: int, referrer_id: int):
    logger.info(f"Обработка реферала: новый {new_user_id}, реферер {referrer_id}")
    new_user = get_user(new_user_id)
    if new_user:
        logger.info(f"Пользователь {new_user_id} уже существует, реферал не засчитан")
        return

    add_or_update_user(new_user_id, None, 0, referrer_id=referrer_id)
    logger.info(f"Новый пользователь {new_user_id} добавлен с реферером {referrer_id}")

    referrer = get_user(referrer_id)
    if referrer:
        new_ref_count = referrer[4] + 1
        add_or_update_user(referrer_id, referrer[0], referrer[1],
                           last_free=referrer[3], used_free=referrer[4],
                           ref_count=new_ref_count,
                           referrer_id=referrer[5],
                           panel_client_id=referrer[6],
                           current_link=referrer[7],
                           ref_link=referrer[8])
        logger.info(f"У реферера {referrer_id} теперь {new_ref_count} рефералов")

        required = int(get_setting("ref_required") or 5)
        if new_ref_count >= required:
            logger.info(f"Реферер {referrer_id} достиг лимита {required}, выдаём бонус")
            await give_ref_bonus(referrer_id)
        else:
            logger.info(f"Реферер {referrer_id} ещё не достиг лимита {required} (сейчас {new_ref_count})")
    else:
        logger.warning(f"Реферер {referrer_id} не найден в БД")

async def give_ref_bonus(tg_id: int):
    logger.info(f"Попытка выдачи бонуса для {tg_id}")
    bonus_days = int(get_setting("ref_bonus_days") or 14)
    try:
        link = await create_subscription(tg_id, bonus_days, "ref_bonus")
        await bot.send_message(
            tg_id,
            f"🎉 *Поздравляем! Вы привели {get_setting('ref_required')} пользователей!*\n"
            f"Вы получили бонусную подписку на {bonus_days} дней!\n"
            f"🔗 Ваша ссылка:\n`{link}`\n\n"
            "📌 Вставьте её в V2RayTun / Happ.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка выдачи бонуса: {e}")
        for admin_id in ADMIN_IDS:
            await bot.send_message(admin_id, f"⚠️ Ошибка при выдаче бонуса пользователю {tg_id}: {e}")

@dp.message(F.text == "👥 Рефералы")
async def referral_cmd(message: types.Message):
    tg_id = message.from_user.id
    user = get_user(tg_id)
    if not user:
        add_or_update_user(tg_id, None, 0)
        user = get_user(tg_id)

    ref_count = user[4] if user else 0
    required = int(get_setting("ref_required") or 5)
    bonus_days = int(get_setting("ref_bonus_days") or 14)

    ref_link = user[8] if user else None
    if not ref_link:
        ref_link = f"ref_{tg_id}"
        add_or_update_user(tg_id, user[0], user[1],
                           last_free=user[3] if user else 0,
                           used_free=user[4] if user else 0,
                           ref_count=ref_count,
                           referrer_id=user[5] if user else None,
                           panel_client_id=user[6] if user else None,
                           current_link=user[7] if user else None,
                           ref_link=ref_link)

    bot_username = BOT_USERNAME
    if not bot_username:
        await message.answer("❌ Ошибка: BOT_USERNAME не задан в config.py.")
        return

    ref_url = f"https://t.me/{bot_username}?start={ref_link}"
    await message.answer(
        f"👥 *Реферальная программа*\n\n"
        f"Приводите друзей и получайте бонусы!\n"
        f"За каждых {required} друзей — +{bonus_days} дней к подписке.\n\n"
        f"📊 *Ваши рефералы:* {ref_count}/{required}\n"
        f"🔗 *Ваша реферальная ссылка:*\n"
        f"`{ref_url}`\n\n"
        "Поделитесь ссылкой с друзьями и получайте бонусы! 🎁",
        parse_mode="Markdown"
    )

# ---------------------------------- ВЫДАЧА БЕСПЛАТНОЙ ПОДПИСКИ ----------------------------------
@dp.callback_query(F.data == "get_free")
async def get_free(callback: types.CallbackQuery):
    logger.info(f"🔔 get_free вызвана для пользователя {callback.from_user.id}")
    # Отвечаем, чтобы убрать "часики"
    await callback.answer()
    tg_id = callback.from_user.id
    user = get_user(tg_id)
    now = int(time.time())

    logger.info(f"Пользователь {tg_id}, данные: {user}")

    # Проверяем активную подписку
    if user and user[1] and user[1] > now:
        logger.info(f"У пользователя уже активна подписка до {user[1]}")
        await callback.message.answer("⏳ У вас уже активная подписка.")
        return

    # Проверяем, использовал ли бесплатную
    if user and user[3] == 1:
        logger.info(f"Пользователь уже использовал бесплатную подписку")
        await callback.message.answer("❌ Вы уже использовали бесплатную подписку.")
        return

    # Проверяем подписку на канал
    if not await check_subscription(tg_id):
        logger.info(f"Пользователь не подписан на канал")
        await callback.message.answer(
            "🔒 *Для получения бесплатной подписки* подпишитесь на наш канал.\n"
            "После подписки нажмите кнопку проверки.",
            parse_mode="Markdown",
            reply_markup=subscribe_keyboard
        )
        return

    # Создаём подписку
    try:
        days = FREE_HOURS // 24
        link = await create_subscription(tg_id, days, "free")
        add_or_update_user(tg_id, "free", int(time.time()) + days*86400, used_free=1)
        logger.info(f"Бесплатная подписка выдана пользователю {tg_id}")
        await callback.message.answer(
            f"✅ *Бесплатная подписка активирована!*\n\n"
            f"▸ Действует до: {format_datetime(int(time.time()) + days*86400)}\n"
            f"🔗 Ваша ссылка:\n`{link}`\n\n"
            "📌 Вставьте её в V2RayTun / Happ.",
            parse_mode="Markdown",
            reply_markup=back_button
        )
    except Exception as e:
        logger.error(f"Ошибка в get_free: {e}", exc_info=True)
        await callback.message.answer(f"❌ Ошибка: {str(e)}")

# ---------------------------------- остальные обработчики ----------------------------------
# (Инструкция, пробный период, покупка, админ-панель и т.д. – они такие же, как были в предыдущей версии, я их не дублирую для краткости)
# Для полноты я приведу их в финальном ответе.

# ---------------------------------- ВЕБ-СЕРВЕР ----------------------------------
async def handle_user_subscription(request):
    path = request.match_info.get('path', '')
    parts = path.split('/')
    if len(parts) != 3:
        return web.Response(text="", status=404)
    tg_id_str, file_type = parts[1], parts[2]
    if file_type not in ("free.txt", "paid.txt"):
        return web.Response(text="", status=404)
    try:
        tg_id = int(tg_id_str)
    except ValueError:
        return web.Response(text="", status=404)

    user = get_user(tg_id)
    if not user or user[1] is None or user[1] <= int(time.time()):
        return web.Response(text="", status=404)

    expire_ts = user[1]
    client_id = user[6]
    if not client_id:
        return web.Response(text="", status=404)
    try:
        link = await panel.get_client_link(client_id)
    except:
        return web.Response(text="", status=404)

    header = f"# {VPN_NAME} - active until: {format_datetime(expire_ts)}\n"
    content = header + link
    return web.Response(text=content, content_type="text/plain")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/user/{path:.*}', handle_user_subscription)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)
    await site.start()
    print(f"✅ Веб-сервер запущен на порту {WEB_SERVER_PORT}")

# ---------------------------------- ЗАПУСК ----------------------------------
async def main():
    init_db()
    asyncio.create_task(start_web_server())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
