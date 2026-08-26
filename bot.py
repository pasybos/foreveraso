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
    except Exception:
        return False

# ---------------------------------- команда /start ----------------------------------
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
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
    expire_ts = int(time.time()) + days * 86400
    email = f"{tariff}_{tg_id}_{int(time.time())}"
    client_id = await panel.create_client(email, expire_ts, total_gb=0, limit_ip=1 if tariff in ("free", "ref_bonus") else 3)
    link = await panel.get_client_link(client_id)
    add_or_update_user(tg_id, tariff, expire_ts, panel_client_id=client_id, current_link=link)
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
    tg_id = callback.from_user.id
    user = get_user(tg_id)
    now = int(time.time())

    if user and user[1] and user[1] > now:
        await callback.answer("У вас уже активная подписка.", show_alert=True)
        return

    if user and user[3] == 1:
        if user[7]:
            if user[1] and user[1] > now:
                time_left = format_time_left(user[1])
                await callback.message.answer(
                    f"🔁 *Ваша бесплатная подписка активна!*\n\n"
                    f"▸ Действует до: `{format_datetime(user[1])}`\n"
                    f"▸ Осталось: `{time_left}`\n"
                    f"🔗 Ваша ссылка:\n`{user[7]}`\n\n"
                    "📌 Вставьте её в V2RayTun / Happ.",
                    parse_mode="Markdown",
                    reply_markup=back_button
                )
                return
            else:
                await callback.answer("❌ Ваша бесплатная подписка истекла.", show_alert=True)
                return
        else:
            await callback.answer("❌ Вы уже использовали бесплатную подписку.", show_alert=True)
            return

    if not await check_subscription(tg_id):
        await callback.message.answer(
            "🔒 *Для получения бесплатной подписки* подпишитесь на наш канал.\n"
            "После подписки нажмите кнопку проверки.",
            parse_mode="Markdown",
            reply_markup=subscribe_keyboard
        )
        return

    try:
        days = FREE_HOURS // 24
        link = await create_subscription(tg_id, days, "free")
        add_or_update_user(tg_id, "free", int(time.time()) + days*86400, used_free=1)
        await callback.message.answer(
            f"✅ *Бесплатная подписка активирована!*\n\n"
            f"▸ Действует до: {format_datetime(int(time.time()) + days*86400)}\n"
            f"🔗 Ваша ссылка:\n`{link}`\n\n"
            "📌 Вставьте её в V2RayTun / Happ.",
            parse_mode="Markdown",
            reply_markup=back_button
        )
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}", parse_mode="Markdown")

# ---------------------------------- МЕНЮ ПОКУПКИ ----------------------------------
@dp.callback_query(F.data == "buy_menu")
async def buy_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Купить за звёзды", callback_data="buy_stars_menu")],
        [InlineKeyboardButton(text="💳 Купить за рубли", callback_data="buy_manual")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ])
    await callback.message.edit_text(
        f"💎 *Выберите способ оплаты:*\n\n"
        "⭐ *Telegram Stars* — мгновенная активация\n"
        "💳 *Рубли* — свяжитесь с администратором для получения реквизитов",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await callback.answer()

# ---------------------------------- ПОКУПКА ЗА ЗВЁЗДЫ ----------------------------------
@dp.callback_query(F.data == "buy_stars_menu")
async def buy_stars_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Неделя (7 дн.) — 25 ⭐", callback_data="stars_week")],
        [InlineKeyboardButton(text=f"Месяц (30 дн.) — 50 ⭐", callback_data="stars_month")],
        [InlineKeyboardButton(text=f"Полгода (180 дн.) — 299 ⭐", callback_data="stars_halfyear")],
        [InlineKeyboardButton(text=f"Год (365 дн.) — 549 ⭐", callback_data="stars_year")],
        [InlineKeyboardButton(text=f"Навсегда (10 лет) — 1350 ⭐", callback_data="stars_forever")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="buy_menu")]
    ])
    await callback.message.edit_text(
        "⭐ *Выберите тариф для оплаты звёздами:*",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("stars_"))
async def buy_stars_tariff(callback: types.CallbackQuery):
    tariff_key = callback.data.split("_")[1]
    tariff_data = TARIFFS.get(tariff_key)
    if not tariff_data:
        await callback.answer("Тариф не найден.", show_alert=True)
        return
    days = tariff_data["days"]
    price = tariff_data["price_stars"]
    tariff_name = TARIFF_NAMES.get(tariff_key, tariff_key)
    await callback.message.answer_invoice(
        title=f"Подписка {VPN_NAME} — {tariff_name}",
        description=f"Доступ к VPN на {days} дней",
        payload=f"stars_{tariff_key}_{callback.from_user.id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=tariff_name, amount=price)],
        start_parameter="sub_stars"
    )
    await callback.answer()

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    payment = message.successful_payment
    payload = payment.invoice_payload
    user_id = message.from_user.id

    parts = payload.split("_")
    if len(parts) != 3 or parts[0] != "stars":
        await message.answer("❌ Ошибка: неверный идентификатор платежа.")
        return
    tariff_key = parts[1]
    tg_id = int(parts[2])
    if tg_id != user_id:
        await message.answer("❌ Ошибка: несовпадение пользователя.")
        return

    tariff_data = TARIFFS.get(tariff_key)
    if not tariff_data:
        await message.answer("❌ Тариф не найден.")
        return
    days = tariff_data["days"]

    try:
        link = await create_subscription(user_id, days, f"paid_{tariff_key}")
        await message.answer(
            f"✅ *Оплата прошла успешно!*\n\n"
            f"▸ Подписка активирована на {days} дней.\n"
            f"▸ Действует до: {format_datetime(int(time.time()) + days*86400)}\n"
            f"🔗 Ваша ссылка:\n`{link}`\n\n"
            "📌 Вставьте её в V2RayTun / Happ.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", parse_mode="Markdown")

# ---------------------------------- РУЧНАЯ ОПЛАТА (через администратора) ----------------------------------
@dp.callback_query(F.data == "buy_manual")
async def buy_manual(callback: types.CallbackQuery):
    await callback.message.edit_text(
        f"💳 *Оплата за рубли*\n\n"
        f"Для покупки подписки свяжитесь с администратором:\n"
        f"📩 **@{PAYMENT_CONTACT}**\n\n"
        f"Он предоставит реквизиты для перевода и активирует подписку после оплаты.\n\n"
        f"📌 *Тарифы:*\n"
        f"▸ Неделя — 35 ₽\n"
        f"▸ Месяц — 99 ₽\n"
        f"▸ Полгода — 549 ₽\n"
        f"▸ Год — 999 ₽\n"
        f"▸ Навсегда — 2499 ₽\n\n"
        f"После оплаты администратор выдаст вам ссылку для подключения.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="buy_menu")]
        ])
    )
    await callback.answer()

# ---------------------------------- КОМАНДА АДМИНИСТРАТОРА /give_sub ----------------------------------
@dp.message(Command("give_sub"))
async def give_sub_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет прав.")
        return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("❌ Использование: /give_sub <telegram_id> <количество_дней>")
        return
    try:
        tg_id = int(args[1])
        days = int(args[2])
        if days <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Неверный формат. ID и дни должны быть числами.")
        return

    try:
        link = await create_subscription(tg_id, days, "admin_give")
        await bot.send_message(
            tg_id,
            f"🎉 *Администратор активировал подписку!*\n\n"
            f"▸ Срок: {days} дней\n"
            f"▸ Действует до: {format_datetime(int(time.time()) + days*86400)}\n"
            f"🔗 Ссылка:\n`{link}`\n\n"
            "📌 Вставьте её в V2RayTun / Happ.",
            parse_mode="Markdown"
        )
        await message.answer(f"✅ Подписка для `{tg_id}` активирована на {days} дней.")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# ---------------------------------- АКТИВАЦИЯ ПОДПИСКИ (админ-панель) ----------------------------------
@dp.message(F.text == "✅ Активировать подписку")
async def admin_activate_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_user_id)
    await message.answer("✏️ Введите *Telegram ID* пользователя (только число):", parse_mode="Markdown")

@dp.message(AdminStates.waiting_for_user_id)
async def admin_activate_get_id(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        tg_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Неверный формат.")
        return
    await state.update_data(tg_id=tg_id)
    await state.set_state(AdminStates.waiting_for_days)
    await message.answer("✏️ Введите *количество дней* подписки:", parse_mode="Markdown")

@dp.message(AdminStates.waiting_for_days)
async def admin_activate_get_days(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        days = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Неверный формат.")
        return
    data = await state.get_data()
    tg_id = data['tg_id']
    await state.clear()
    try:
        link = await create_subscription(tg_id, days, "admin_activate")
        await bot.send_message(
            tg_id,
            f"🎉 *Подписка активирована администратором!*\n\n"
            f"▸ Срок: {days} дней\n"
            f"▸ Действует до: {format_datetime(int(time.time()) + days*86400)}\n"
            f"🔗 Ссылка:\n`{link}`",
            parse_mode="Markdown"
        )
        await message.answer(f"✅ Подписка для `{tg_id}` активирована на {days} дней.", reply_markup=admin_keyboard)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=admin_keyboard)

# ---------------------------------- РЕФЕРАЛЬНАЯ ПОДПИСКА (админ) ----------------------------------
@dp.message(F.text == "✅ Активировать реферальную подписку")
async def admin_ref_activate_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_ref_user_id)
    await message.answer("✏️ Введите *Telegram ID* пользователя (только число):", parse_mode="Markdown")

@dp.message(AdminStates.waiting_for_ref_user_id)
async def admin_ref_activate_get_id(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        tg_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Неверный формат.")
        return
    await state.update_data(tg_id=tg_id)
    await state.set_state(AdminStates.waiting_for_ref_days)
    await message.answer("✏️ Введите *количество дней* реферальной подписки (обычно 14):", parse_mode="Markdown")

@dp.message(AdminStates.waiting_for_ref_days)
async def admin_ref_activate_get_days(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        days = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Неверный формат.")
        return
    data = await state.get_data()
    tg_id = data['tg_id']
    await state.clear()
    try:
        link = await create_subscription(tg_id, days, "ref_bonus")
        await bot.send_message(
            tg_id,
            f"🎉 *Реферальная подписка активирована администратором!*\n\n"
            f"▸ Срок: {days} дней\n"
            f"▸ Действует до: {format_datetime(int(time.time()) + days*86400)}\n"
            f"🔗 Ссылка:\n`{link}`",
            parse_mode="Markdown"
        )
        await message.answer(f"✅ Реферальная подписка для `{tg_id}` активирована на {days} дней.", reply_markup=admin_keyboard)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=admin_keyboard)

# ---------------------------------- РЕФЕРАЛЬНЫЕ НАСТРОЙКИ ----------------------------------
@dp.message(F.text == "⚙️ Реферальные настройки")
async def admin_ref_settings(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_ref_settings)
    current_required = get_setting("ref_required") or 5
    current_bonus = get_setting("ref_bonus_days") or 14
    await message.answer(
        f"⚙️ *Текущие настройки рефералов:*\n"
        f"▸ Требуется приглашений: {current_required}\n"
        f"▸ Бонусных дней: {current_bonus}\n\n"
        "Чтобы изменить, отправьте новое значение в формате:\n"
        "`приглашений|дней`\nНапример: `5|14`\nДля отмены /cancel",
        parse_mode="Markdown"
    )

@dp.message(AdminStates.waiting_for_ref_settings)
async def admin_ref_settings_input(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=admin_keyboard)
        return
    parts = message.text.split("|")
    if len(parts) != 2:
        await message.answer("❌ Неверный формат. Используйте: `приглашений|дней`")
        return
    try:
        required = int(parts[0].strip())
        bonus = int(parts[1].strip())
        if required <= 0 or bonus <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительные числа.")
        return
    set_setting("ref_required", str(required))
    set_setting("ref_bonus_days", str(bonus))
    await state.clear()
    await message.answer(f"✅ Настройки обновлены: требуется {required} приглашений, бонус {bonus} дней.", reply_markup=admin_keyboard)

# ---------------------------------- ПРОМОКОДЫ ----------------------------------
@dp.message(F.text == "🎫 Создать промокод")
async def admin_create_promo_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_promo_days)
    await message.answer("✏️ Введите *количество дней*, которое даёт промокод:", parse_mode="Markdown")

@dp.message(AdminStates.waiting_for_promo_days)
async def admin_create_promo_days(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        days = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите число.")
        return
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    add_promocode(code, days)
    await state.clear()
    await message.answer(f"✅ Промокод `{code}` создан на {days} дней.", parse_mode="Markdown", reply_markup=admin_keyboard)

@dp.message(F.text == "📋 Список промокодов")
async def admin_list_promocodes(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    promos = get_all_promocodes()
    if not promos:
        await message.answer("📭 Промокодов пока нет.", reply_markup=admin_keyboard)
        return
    text = "📋 *Список промокодов:*\n\n"
    for code, days, used_by, created_at, used_at in promos:
        status = "✅ Использован" if used_by else "🟢 Активен"
        used_info = f" (использовал {used_by})" if used_by else ""
        text += f"▸ `{code}` – {days} дней – {status}{used_info}\n"
    await message.answer(text, parse_mode="Markdown", reply_markup=admin_keyboard)

@dp.message(F.text == "🎫 Промокод")
async def promo_cmd(message: types.Message, state: FSMContext):
    await state.set_state(UserStates.waiting_for_promo_code)
    await message.answer("🎫 Введите промокод:", parse_mode="Markdown")

@dp.message(UserStates.waiting_for_promo_code)
async def process_promo_code(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    promo = get_promocode(code)
    if not promo:
        await message.answer("❌ Неверный промокод.")
        return
    code_text, days, used_by, used_at = promo
    if used_by:
        await message.answer("❌ Промокод уже использован.")
        return
    tg_id = message.from_user.id
    user = get_user(tg_id)
    if user and user[1] and user[1] > int(time.time()):
        new_expire = user[1] + days * 86400
        add_or_update_user(tg_id, user[0], new_expire, panel_client_id=user[6], current_link=user[7])
    else:
        try:
            link = await create_subscription(tg_id, days, "promo")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}")
            await state.clear()
            return
    use_promocode(code, tg_id)
    await state.clear()
    await message.answer(f"✅ Промокод активирован! Добавлено {days} дней.", reply_markup=bottom_menu)

# ---------------------------------- ПРОФИЛЬ ----------------------------------
@dp.message(F.text == "👤 Профиль")
async def profile_cmd(message: types.Message):
    tg_id = message.from_user.id
    user = get_user(tg_id)
    if not user or user[1] is None or user[1] == 0:
        await message.answer("📭 У вас нет активной подписки.")
        return
    tariff, expire_ts, _, _, _, _, _, link = user
    now = int(time.time())
    if expire_ts <= now:
        await message.answer("⏳ Подписка истекла.")
        delete_user(tg_id)
        return
    time_left = format_time_left(expire_ts)
    await message.answer(
        f"👤 *Ваш профиль*\n\n"
        f"▸ Тариф: {tariff.upper()}\n"
        f"▸ Осталось: {time_left}\n"
        f"▸ Истекает: {format_datetime(expire_ts)}\n"
        f"🔗 Ссылка: {link[:30]}..." if link else "",
        parse_mode="Markdown"
    )

# ---------------------------------- ДРУГИЕ КНОПКИ ----------------------------------
@dp.message(F.text == "📢 Канал")
async def channel_cmd(message: types.Message):
    await message.answer(f"📢 Наш канал: {CHANNEL_ID}")

@dp.message(F.text == "❓ Поддержка")
async def support_cmd(message: types.Message):
    await message.answer(f"❓ По вопросам пишите: {PAYMENT_CONTACT}")

@dp.message(F.text == "📜 Соглашение")
async def agreement_cmd(message: types.Message):
    await message.answer("📜 Пользовательское соглашение: https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📄 Открыть", url="https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19")]]))

@dp.message(F.text == "ℹ️ Политика")
async def policy_cmd(message: types.Message):
    await message.answer("ℹ️ Политика конфиденциальности: https://telegra.ph/Politika-konfidencialnosti-06-11-43", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📄 Открыть", url="https://telegra.ph/Politika-konfidencialnosti-06-11-43")]]))

# ---------------------------------- СТАТИСТИКА, СПИСОК ПОЛЬЗОВАТЕЛЕЙ, РАССЫЛКА ----------------------------------
@dp.message(F.text == "👥 Список пользователей")
async def admin_list_users(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    users = get_all_active_users()
    if not users:
        await message.answer("📭 Активных пользователей нет.")
        return
    text = "👥 Активные пользователи:\n\n"
    for tg_id, expire_ts in users:
        user = get_user(tg_id)
        if user:
            tariff = user[0] or "неизвестно"
            time_left = format_time_left(expire_ts)
            text += f"▸ ID `{tg_id}` – {tariff}, осталось {time_left}\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📊 Статистика")
async def admin_stats(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users')
    total = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE expire_time > ?', (int(time.time()),))
    active = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE tariff="free"')
    free_count = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE tariff="paid"')
    paid_count = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE tariff="promo"')
    promo_count = c.fetchone()[0]
    conn.close()
    await message.answer(
        f"📊 Статистика {VPN_NAME}\n\n"
        f"▸ Всего записей: {total}\n"
        f"▸ Активных: {active}\n"
        f"▸ Бесплатных: {free_count}\n"
        f"▸ Платных: {paid_count}\n"
        f"▸ По промокодам: {promo_count}",
        parse_mode="Markdown"
    )

@dp.message(F.text == "📨 Сделать рассылку")
async def admin_broadcast_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_broadcast_text)
    await message.answer("✏️ Введите текст рассылки (можно Markdown). Для отмены /cancel", parse_mode="Markdown")

@dp.message(AdminStates.waiting_for_broadcast_text)
async def admin_broadcast_get_text(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=admin_keyboard)
        return
    text = message.text
    await state.update_data(broadcast_text=text)
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast_confirm")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="broadcast_cancel")]
    ])
    await message.answer(
        "📨 *Предпросмотр:*\n\n" + text + "\n\nОтправить всем?",
        parse_mode="Markdown",
        reply_markup=confirm_kb
    )
    await state.set_state(AdminStates.waiting_for_broadcast_confirm)

@dp.callback_query(F.data == "broadcast_confirm")
async def admin_broadcast_confirm(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Доступ запрещён.", show_alert=True)
        return
    data = await state.get_data()
    text = data.get("broadcast_text")
    if not text:
        await callback.message.edit_text("❌ Текст не найден.")
        await state.clear()
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT tg_id FROM users')
    rows = c.fetchall()
    conn.close()
    if not rows:
        await callback.message.edit_text("📭 Нет пользователей.")
        await state.clear()
        return
    sent = 0
    failed = 0
    for (tg_id,) in rows:
        try:
            await bot.send_message(tg_id, text, parse_mode="Markdown")
            sent += 1
            await asyncio.sleep(0.1)
        except:
            failed += 1
    await callback.message.edit_text(f"✅ Рассылка завершена!\n▸ Отправлено: {sent}\n▸ Не удалось: {failed}")
    await state.clear()

@dp.callback_query(F.data == "broadcast_cancel")
async def admin_broadcast_cancel(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Доступ запрещён.", show_alert=True)
        return
    await callback.message.edit_text("❌ Рассылка отменена.")
    await state.clear()

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
