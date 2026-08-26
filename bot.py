import asyncio
import time
import sqlite3
import os
import random
import string
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
import aiohttp

from config import BOT_TOKEN, ADMIN_IDS, FREE_HOURS, PAID_DAYS, PAID_PRICE, VPN_NAME, DB_PATH, CHANNEL_ID, PAYMENT_CONTACT, IMAGE_PATH, PUBLIC_URL, WEB_SERVER_HOST, WEB_SERVER_PORT, BOT_USERNAME
from database import init_db, get_user, add_or_update_user, delete_user, get_all_active_users, add_promocode, get_promocode, use_promocode, get_all_promocodes, get_free_link, mark_link_used, get_all_pool_links, add_pool_link, delete_pool_link, get_free_ref_link, mark_ref_link_used, get_all_ref_pool_links, add_ref_pool_link, delete_ref_pool_link, get_setting, set_setting
from panel_api import PanelAPI
from utils import format_time_left, format_datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
panel = PanelAPI()

# ---------------------------------- состояния ----------------------------------
class AdminStates(StatesGroup):
    waiting_for_user_id = State()                 # для обычной активации
    waiting_for_days = State()
    waiting_for_ref_user_id = State()             # для реферальной активации
    waiting_for_ref_days = State()
    waiting_for_promo_days = State()
    waiting_for_broadcast_text = State()
    waiting_for_broadcast_confirm = State()
    waiting_for_link_input = State()              # для обычных ссылок
    waiting_for_link_delete = State()
    waiting_for_ref_link_input = State()          # для реферальных ссылок
    waiting_for_ref_link_delete = State()
    waiting_for_ref_settings = State()

class UserStates(StatesGroup):
    waiting_for_promo_code = State()

# ---------------------------------- КНОПКИ ----------------------------------
main_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📖 Инструкция", callback_data="instructions")],
    [InlineKeyboardButton(text="🚀 Получить подписку", callback_data="get_free")],
    [InlineKeyboardButton(text="💎 Купить VIP", callback_data="buy_paid")],
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
        [KeyboardButton(text="📦 Управление обычными ссылками")],
        [KeyboardButton(text="📦 Управление реферальными ссылками")],
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
    link_data = get_free_ref_link()
    if not link_data:
        logger.warning(f"Нет свободных реферальных ссылок для {tg_id}")
        for admin_id in ADMIN_IDS:
            await bot.send_message(admin_id, f"⚠️ Закончились реферальные ссылки! Пользователь {tg_id} не получил бонус.")
        return
    link_id, link = link_data
    mark_ref_link_used(link_id, tg_id)
    logger.info(f"Выдана реферальная ссылка {link} для {tg_id}")

    bonus_days = int(get_setting("ref_bonus_days") or 14)
    expire_ts = int(time.time()) + bonus_days * 86400

    user = get_user(tg_id)
    if user and user[1] and user[1] > int(time.time()):
        new_expire = user[1] + bonus_days * 86400
    else:
        new_expire = expire_ts
    add_or_update_user(tg_id, "ref_bonus", new_expire,
                       last_free=user[3] if user else 0,
                       used_free=user[4] if user else 0,
                       ref_count=user[4] if user else 0,
                       referrer_id=user[5] if user else None,
                       panel_client_id=user[6] if user else None,
                       current_link=link,
                       ref_link=user[8] if user else None)

    await bot.send_message(
        tg_id,
        f"🎉 *Поздравляем! Вы привели {get_setting('ref_required')} пользователей!*\n"
        f"Вы получили бонусную подписку на {bonus_days} дней!\n"
        f"🔗 Ваша ссылка:\n`{link}`\n\n"
        "📌 Вставьте её в V2RayTun / Happ как подписку.",
        parse_mode="Markdown"
    )
    logger.info(f"Бонус выдан для {tg_id}")

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

# ---------------------------------- АДМИН-ПАНЕЛЬ ----------------------------------
# Обычные ссылки
@dp.message(F.text == "📦 Управление обычными ссылками")
async def manage_links(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить обычные ссылки")],
            [KeyboardButton(text="📋 Список обычных ссылок")],
            [KeyboardButton(text="🗑️ Удалить обычную ссылку")],
            [KeyboardButton(text="🔙 Назад в админку")]
        ],
        resize_keyboard=True
    )
    await message.answer("📦 *Управление обычными ссылками*\n(ссылки для обычных подписок)", parse_mode="Markdown", reply_markup=kb)

@dp.message(F.text == "➕ Добавить обычные ссылки")
async def add_links_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.clear()
    await state.set_state(AdminStates.waiting_for_link_input)
    await message.answer("✏️ Введите обычные ссылки (vless://, vmess://, trojan://) — каждая с новой строки, или отправьте .txt файл. Для отмены /cancel", parse_mode="Markdown")

@dp.message(AdminStates.waiting_for_link_input, F.document)
async def add_links_from_file(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    document = message.document
    if document.mime_type != "text/plain":
        await message.answer("❌ Отправьте текстовый файл (.txt).")
        return
    file = await bot.get_file(document.file_id)
    file_bytes = await bot.download_file(file.file_path)
    content = file_bytes.getvalue().decode('utf-8', errors='ignore')
    lines = content.splitlines()
    added = 0
    skipped = 0
    for link in lines:
        link = link.strip()
        if link.startswith(("vless://", "vmess://", "trojan://")):
            try:
                add_pool_link(link)
                added += 1
            except:
                skipped += 1
        else:
            skipped += 1
    await state.clear()
    await message.answer(f"✅ Добавлено {added} обычных ссылок, пропущено {skipped} (неверный формат/дубликат).", reply_markup=admin_keyboard)

@dp.message(AdminStates.waiting_for_link_input, F.text)
async def add_links_process(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=admin_keyboard)
        return
    links = message.text.strip().splitlines()
    added = 0
    skipped = 0
    for link in links:
        link = link.strip()
        if link.startswith(("vless://", "vmess://", "trojan://")):
            try:
                add_pool_link(link)
                added += 1
            except:
                skipped += 1
        else:
            skipped += 1
    await state.clear()
    await message.answer(f"✅ Добавлено {added} обычных ссылок, пропущено {skipped} (неверный формат/дубликат).", reply_markup=admin_keyboard)

@dp.message(F.text == "📋 Список обычных ссылок")
async def list_links(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    links = get_all_pool_links()
    if not links:
        await message.answer("📭 Пул обычных ссылок пуст.", reply_markup=admin_keyboard)
        return
    text = "📋 *Список обычных ссылок:*\n\n"
    for link_id, link, used, used_by in links:
        status = "❌ Использована" if used else "✅ Свободна"
        used_info = f" (пользователь {used_by})" if used_by else ""
        text += f"ID `{link_id}`: `{link[:50]}...` — {status}{used_info}\n"
    await message.answer(text, parse_mode="Markdown", reply_markup=admin_keyboard)

@dp.message(F.text == "🗑️ Удалить обычную ссылку")
async def delete_link_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.clear()
    await state.set_state(AdminStates.waiting_for_link_delete)
    await message.answer("✏️ Введите ID ссылки для удаления. Для отмены /cancel", parse_mode="Markdown")

@dp.message(AdminStates.waiting_for_link_delete)
async def delete_link_process(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=admin_keyboard)
        return
    try:
        link_id = int(message.text.strip())
        delete_pool_link(link_id)
        await message.answer(f"✅ Обычная ссылка с ID `{link_id}` удалена.", parse_mode="Markdown", reply_markup=admin_keyboard)
    except ValueError:
        await message.answer("❌ Неверный ID, введите число.", reply_markup=admin_keyboard)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=admin_keyboard)
    await state.clear()

# Реферальные ссылки
@dp.message(F.text == "📦 Управление реферальными ссылками")
async def manage_ref_links(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить реферальные ссылки")],
            [KeyboardButton(text="📋 Список реферальных ссылок")],
            [KeyboardButton(text="🗑️ Удалить реферальную ссылку")],
            [KeyboardButton(text="🔙 Назад в админку")]
        ],
        resize_keyboard=True
    )
    await message.answer("📦 *Управление реферальными ссылками*\n(бонус за приглашения)", parse_mode="Markdown", reply_markup=kb)

@dp.message(F.text == "➕ Добавить реферальные ссылки")
async def add_ref_links_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.clear()
    await state.set_state(AdminStates.waiting_for_ref_link_input)
    await message.answer("✏️ Введите реферальные ссылки (vless://, vmess://, trojan://) — каждая с новой строки, или отправьте .txt файл. Для отмены /cancel", parse_mode="Markdown")

@dp.message(AdminStates.waiting_for_ref_link_input, F.document)
async def add_ref_links_from_file(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    document = message.document
    if document.mime_type != "text/plain":
        await message.answer("❌ Отправьте текстовый файл (.txt).")
        return
    file = await bot.get_file(document.file_id)
    file_bytes = await bot.download_file(file.file_path)
    content = file_bytes.getvalue().decode('utf-8', errors='ignore')
    lines = content.splitlines()
    added = 0
    skipped = 0
    for link in lines:
        link = link.strip()
        if link.startswith(("vless://", "vmess://", "trojan://")):
            try:
                add_ref_pool_link(link)
                added += 1
            except:
                skipped += 1
        else:
            skipped += 1
    await state.clear()
    await message.answer(f"✅ Добавлено {added} реферальных ссылок, пропущено {skipped} (неверный формат/дубликат).", reply_markup=admin_keyboard)

@dp.message(AdminStates.waiting_for_ref_link_input, F.text)
async def add_ref_links_process(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=admin_keyboard)
        return
    links = message.text.strip().splitlines()
    added = 0
    skipped = 0
    for link in links:
        link = link.strip()
        if link.startswith(("vless://", "vmess://", "trojan://")):
            try:
                add_ref_pool_link(link)
                added += 1
            except:
                skipped += 1
        else:
            skipped += 1
    await state.clear()
    await message.answer(f"✅ Добавлено {added} реферальных ссылок, пропущено {skipped} (неверный формат/дубликат).", reply_markup=admin_keyboard)

@dp.message(F.text == "📋 Список реферальных ссылок")
async def list_ref_links(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    links = get_all_ref_pool_links()
    if not links:
        await message.answer("📭 Реферальный пул ссылок пуст.", reply_markup=admin_keyboard)
        return
    text = "📋 *Список реферальных ссылок:*\n\n"
    for link_id, link, used, used_by in links:
        status = "❌ Использована" if used else "✅ Свободна"
        used_info = f" (пользователь {used_by})" if used_by else ""
        text += f"ID `{link_id}`: `{link[:50]}...` — {status}{used_info}\n"
    await message.answer(text, parse_mode="Markdown", reply_markup=admin_keyboard)

@dp.message(F.text == "🗑️ Удалить реферальную ссылку")
async def delete_ref_link_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.clear()
    await state.set_state(AdminStates.waiting_for_ref_link_delete)
    await message.answer("✏️ Введите ID реферальной ссылки для удаления. Для отмены /cancel", parse_mode="Markdown")

@dp.message(AdminStates.waiting_for_ref_link_delete)
async def delete_ref_link_process(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=admin_keyboard)
        return
    try:
        link_id = int(message.text.strip())
        delete_ref_pool_link(link_id)
        await message.answer(f"✅ Реферальная ссылка с ID `{link_id}` удалена.", parse_mode="Markdown", reply_markup=admin_keyboard)
    except ValueError:
        await message.answer("❌ Неверный ID, введите число.", reply_markup=admin_keyboard)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=admin_keyboard)
    await state.clear()

# Реферальные настройки
@dp.message(F.text == "⚙️ Реферальные настройки")
async def admin_ref_settings(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.clear()
    await state.set_state(AdminStates.waiting_for_ref_settings)
    current_required = get_setting("ref_required") or 5
    current_bonus = get_setting("ref_bonus_days") or 14
    await message.answer(
        f"⚙️ *Текущие настройки рефералов:*\n"
        f"▸ Требуется приглашений: `{current_required}`\n"
        f"▸ Бонусных дней: `{current_bonus}`\n\n"
        "Чтобы изменить, отправьте новое значение в формате:\n"
        "`количество_приглашений|количество_дней`\n"
        "Например: `5|14`\n\n"
        "Для отмены введите /cancel",
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
        await message.answer("❌ Неверный формат. Используйте: `приглашений|дней`\nНапример: `5|14`", parse_mode="Markdown")
        return
    try:
        required = int(parts[0].strip())
        bonus = int(parts[1].strip())
        if required <= 0 or bonus <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительные числа.", parse_mode="Markdown")
        return
    set_setting("ref_required", str(required))
    set_setting("ref_bonus_days", str(bonus))
    await state.clear()
    await message.answer(f"✅ Настройки обновлены: требуется {required} приглашений, бонус {bonus} дней.", reply_markup=admin_keyboard)

# Активация обычной подписки (админ)
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
        await message.answer("❌ Неверный формат. Введите число.")
        return
    await state.update_data(tg_id=tg_id)
    await state.set_state(AdminStates.waiting_for_days)
    await message.answer("✏️ Введите *количество дней* подписки (например, 30, 7, 1):", parse_mode="Markdown")

@dp.message(AdminStates.waiting_for_days)
async def admin_activate_get_days(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное число.")
        return
    data = await state.get_data()
    tg_id = data['tg_id']
    await state.clear()

    # Получаем ссылку из обычного пула
    link_data = get_free_link()
    if not link_data:
        await message.answer("❌ Нет свободных обычных ссылок. Пополните пул.")
        return
    link_id, link = link_data
    mark_link_used(link_id, tg_id)
    expire_ts = int(time.time()) + days * 86400
    add_or_update_user(tg_id, "paid", expire_ts, panel_client_id=None, current_link=link)

    await bot.send_message(
        tg_id,
        f"🎉 *Ваша подписка активирована администратором!*\n\n"
        f"▸ Срок: {days} дней\n"
        f"▸ Действует до: {format_datetime(expire_ts)}\n"
        f"🔗 Ссылка:\n`{link}`",
        parse_mode="Markdown"
    )
    await message.answer(f"✅ Подписка для `{tg_id}` активирована на {days} дней.", reply_markup=admin_keyboard)

# Активация реферальной подписки (админ)
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
        await message.answer("❌ Неверный формат. Введите число.")
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
        if days <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное число.")
        return
    data = await state.get_data()
    tg_id = data['tg_id']
    await state.clear()

    # Получаем ссылку из реферального пула
    link_data = get_free_ref_link()
    if not link_data:
        await message.answer("❌ Нет свободных реферальных ссылок. Пополните реферальный пул.")
        return
    link_id, link = link_data
    mark_ref_link_used(link_id, tg_id)
    expire_ts = int(time.time()) + days * 86400
    add_or_update_user(tg_id, "ref_bonus", expire_ts, panel_client_id=None, current_link=link)

    await bot.send_message(
        tg_id,
        f"🎉 *Реферальная подписка активирована администратором!*\n\n"
        f"▸ Срок: {days} дней\n"
        f"▸ Действует до: {format_datetime(expire_ts)}\n"
        f"🔗 Ссылка:\n`{link}`",
        parse_mode="Markdown"
    )
    await message.answer(f"✅ Реферальная подписка для `{tg_id}` активирована на {days} дней.", reply_markup=admin_keyboard)

# ---------------------------------- ОСТАЛЬНЫЕ ОБРАБОТЧИКИ (без изменений) ----------------------------------
# Здесь должны быть функции: get_free, buy_paid, profile, promo_cmd, channel, support, agreement, policy, admin_exit, admin_list_users, admin_stats, admin_create_promo, admin_list_promocodes, admin_broadcast, handle_user_subscription, start_web_server, main.
# Для краткости я их не дублирую, но они есть в предыдущих версиях и должны быть включены в финальный файл.
# Если нужно, я могу их добавить, но они не изменились.

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
