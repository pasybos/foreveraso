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

from config import BOT_TOKEN, ADMIN_IDS, FREE_HOURS, PAID_DAYS, PAID_PRICE, VPN_NAME, DB_PATH, CHANNEL_ID, PAYMENT_CONTACT, IMAGE_PATH
from database import init_db, get_user, add_or_update_user, delete_user, get_all_active_users, add_promocode, get_promocode, use_promocode, get_all_promocodes, get_free_link, mark_link_used, get_all_pool_links, add_pool_link, delete_pool_link
from utils import format_time_left, format_datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ---------------------------------- состояния ----------------------------------
class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_days = State()
    waiting_for_promo_days = State()
    waiting_for_broadcast_text = State()
    waiting_for_broadcast_confirm = State()
    waiting_for_link_input = State()
    waiting_for_link_delete = State()

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
        [KeyboardButton(text="🎫 Создать промокод")],
        [KeyboardButton(text="📋 Список промокодов")],
        [KeyboardButton(text="📨 Сделать рассылку")],
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="📦 Управление ссылками")],
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
        ref_id = args[1]
        if ref_id.isdigit() and int(ref_id) != message.from_user.id:
            await handle_referral(message.from_user.id, int(ref_id))

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
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT tg_id FROM users WHERE tg_id=?', (new_user_id,))
    if c.fetchone():
        conn.close()
        return
    c.execute(''' 
        INSERT OR IGNORE INTO users (tg_id, tariff, expire_time, ref_count, referrer_id)
        VALUES (?, NULL, 0, 0, ?)
    ''', (new_user_id, referrer_id))
    c.execute('UPDATE users SET ref_count = ref_count + 1 WHERE tg_id=?', (referrer_id,))
    conn.commit()
    c.execute('SELECT ref_count, expire_time, tariff FROM users WHERE tg_id=?', (referrer_id,))
    row = c.fetchone()
    conn.close()
    if row and row[0] >= 3:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('UPDATE users SET ref_count = 0 WHERE tg_id=?', (referrer_id,))
        conn.commit()
        conn.close()
        user = get_user(referrer_id)
        if user and user[1] and user[1] > int(time.time()):
            new_expire = user[1] + 86400
        else:
            new_expire = int(time.time()) + 86400
        add_or_update_user(referrer_id, user[0] if user else "free", new_expire)
        try:
            await bot.send_message(
                referrer_id,
                "🎉 *Вы привели 3 пользователей!*\n"
                "Ваша подписка продлена на +1 день!",
                parse_mode="Markdown"
            )
        except:
            pass

@dp.message(F.text == "👥 Рефералы")
async def referral_cmd(message: types.Message):
    tg_id = message.from_user.id
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT ref_count FROM users WHERE tg_id=?', (tg_id,))
    row = c.fetchone()
    ref_count = row[0] if row else 0
    conn.close()
    ref_link = f"https://t.me/{bot.username}?start={tg_id}"
    await message.answer(
        f"👥 *Реферальная программа*\n\n"
        f"Приводите друзей и получайте бонусы!\n"
        f"За каждых 3 друзей — +1 день к подписке.\n\n"
        f"📊 *Ваши рефералы:* {ref_count}/3\n"
        f"🔗 *Ваша реферальная ссылка:*\n"
        f"`{ref_link}`\n\n"
        "Поделитесь ссылкой с друзьями и получайте бонусы! 🎁",
        parse_mode="Markdown"
    )

# ---------------------------------- обработчики callback'ов ----------------------------------
@dp.callback_query(F.data == "back_main")
async def back_main(callback: types.CallbackQuery):
    await callback.message.edit_text("📌 *Главное меню*", parse_mode="Markdown", reply_markup=main_menu)

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if await check_subscription(user_id):
        await callback.answer("✅ Подписка подтверждена!", show_alert=True)
        await get_free(callback)
    else:
        await callback.answer("❌ Вы ещё не подписаны. Сделайте это и нажмите «Проверить подписку».", show_alert=True)

@dp.callback_query(F.data == "instructions")
async def show_instructions(callback: types.CallbackQuery):
    instructions_text = (
        "📖 *Инструкция по подключению VPN*\n\n"
        "1. Нажмите «Получить подписку» или «Пробный период»\n"
        "2. Бот даст вам ссылку-подписку\n"
        "3. Скопируйте ссылку\n"
        "4. Откройте V2RayTun или Happ\n"
        "5. Вставьте ссылку как новое подключение\n"
        "6. Подключитесь\n\n"
        "❓ Если нужна помощь — обратитесь в поддержку."
    )
    await callback.message.edit_text(instructions_text, parse_mode="Markdown", reply_markup=back_button)

@dp.callback_query(F.data == "trial")
async def trial_handler(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🎁 *Пробный период*\n\n"
        "Вы можете получить бесплатную подписку на 24 часа.\n"
        "Для этого нажмите «Получить подписку».\n\n"
        "⚠️ Бесплатная подписка доступна только один раз.",
        parse_mode="Markdown",
        reply_markup=back_button
    )

# ---------------------------------- ВЫДАЧА ПОДПИСКИ (из пула) ----------------------------------
async def assign_link_to_user(tg_id: int, tariff: str, expire_ts: int) -> str:
    link_data = get_free_link()
    if not link_data:
        raise Exception("Нет свободных ссылок. Обратитесь к администратору.")
    link_id, link = link_data
    mark_link_used(link_id, tg_id)
    add_or_update_user(tg_id, tariff, expire_ts, subscription_link=link)
    return link

@dp.callback_query(F.data == "get_free")
async def get_free(callback: types.CallbackQuery):
    tg_id = callback.from_user.id
    user = get_user(tg_id)
    now = int(time.time())

    if user and user[1] and user[1] > now:
        await callback.answer("У вас уже активная подписка.", show_alert=True)
        return

    if user and user[3] == 1:
        if user[6]:
            if user[1] and user[1] > now:
                time_left = format_time_left(user[1])
                await callback.message.answer(
                    f"🔁 *Ваша бесплатная подписка активна!*\n\n"
                    f"▸ Действует до: `{format_datetime(user[1])}`\n"
                    f"▸ Осталось: `{time_left}`\n"
                    f"🔗 *Ваша ссылка:*\n`{user[6]}`\n\n"
                    "📌 Скопируйте ссылку и вставьте в V2RayTun/Happ.",
                    parse_mode="Markdown",
                    reply_markup=back_button
                )
                return
            else:
                await callback.answer("❌ Ваша бесплатная подписка истекла. Теперь доступен только платный тариф.", show_alert=True)
                return
        else:
            await callback.answer("❌ Вы уже использовали бесплатную подписку. Теперь доступен только платный тариф.", show_alert=True)
            return

    if not await check_subscription(tg_id):
        await callback.message.edit_text(
            "🔒 *Для получения подписки* подпишитесь на наш канал.\n"
            "После подписки нажмите кнопку проверки.",
            parse_mode="Markdown",
            reply_markup=subscribe_keyboard
        )
        return

    try:
        expire_ts = now + FREE_HOURS * 3600
        link = await assign_link_to_user(tg_id, "free", expire_ts)
        await callback.message.answer(
            f"✅ *Бесплатная подписка активирована!*\n\n"
            f"▸ Действует до: `{format_datetime(expire_ts)}`\n"
            f"🔗 *Ваша ссылка:*\n`{link}`\n\n"
            "📌 Скопируйте ссылку и вставьте в V2RayTun/Happ.\n"
            "⚠️ *Если вы потеряете ссылку, вы можете запросить её снова в течение 24 часов.*\n"
            "По истечении срока бесплатная подписка станет недоступна, и вы сможете только купить VIP.",
            parse_mode="Markdown",
            reply_markup=back_button
        )
    except Exception as e:
        await callback.message.answer(
            f"❌ *Ошибка при создании подписки:*\n{str(e)}",
            parse_mode="Markdown"
        )

# ---------------------------------- ПОКУПКА VIP ----------------------------------
@dp.callback_query(F.data == "buy_paid")
async def buy_paid(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data="pay_confirm")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ])
    await callback.message.edit_text(
        f"💎 *VIP-тариф {VPN_NAME}*\n\n"
        f"▸ Срок: `{PAID_DAYS}` дней\n"
        f"▸ Стоимость: `{PAID_PRICE}`\n\n"
        f"💳 *Реквизиты для оплаты:*\n"
        f"Переведите сумму на `{PAYMENT_CONTACT}`\n\n"
        "После перевода нажмите кнопку ниже, чтобы администратор получил уведомление.",
        parse_mode="Markdown",
        reply_markup=kb
    )

@dp.callback_query(F.data == "pay_confirm")
async def pay_confirm(callback: types.CallbackQuery):
    user = callback.from_user
    for admin_id in ADMIN_IDS:
        await bot.send_message(
            admin_id,
            f"💳 *Заявка на оплату*\n"
            f"Пользователь: @{user.username} (ID: `{user.id}`)\n"
            f"Тариф: VIP (30 дней)\n"
            f"Активируйте через админ-панель (команда /admin)."
        )
    await callback.message.edit_text(
        "✅ *Заявка отправлена!*\n\n"
        "Администратор проверит оплату в ближайшее время.",
        parse_mode="Markdown",
        reply_markup=back_button
    )

# ---------------------------------- ПРОФИЛЬ ----------------------------------
@dp.message(F.text == "👤 Профиль")
async def profile_cmd(message: types.Message):
    tg_id = message.from_user.id
    user = get_user(tg_id)
    if not user or user[1] is None or user[1] == 0:
        await message.answer("📭 *У вас пока нет активной подписки.*", parse_mode="Markdown")
        return

    tariff, expire_ts, _, used_free, _, _, link = user
    now = int(time.time())
    if expire_ts <= now:
        await message.answer("⏳ *Срок подписки истёк.* Приобретите новую.", parse_mode="Markdown")
        delete_user(tg_id)
        return

    time_left = format_time_left(expire_ts)
    await message.answer(
        f"👤 *{VPN_NAME}*\n\n"
        f"▸ Тариф: `{tariff.upper()}`\n"
        f"▸ Осталось: `{time_left}`\n"
        f"▸ Истекает: `{format_datetime(expire_ts)}`\n"
        f"🔗 Ссылка: `{link[:30]}...`" if link else "",
        parse_mode="Markdown"
    )

# ---------------------------------- ПРОМОКОД ----------------------------------
@dp.message(F.text == "🎫 Промокод")
async def promo_cmd(message: types.Message, state: FSMContext):
    await state.set_state(UserStates.waiting_for_promo_code)
    await message.answer(
        "🎫 *Введите промокод:*\n\n"
        "Введите код, который вы получили.\n"
        "Если у вас нет промокода, вы можете получить его у администратора.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🔙 Отмена")]],
            resize_keyboard=True
        )
    )

@dp.message(UserStates.waiting_for_promo_code)
async def process_promo_code(message: types.Message, state: FSMContext):
    if message.text == "🔙 Отмена":
        await state.clear()
        await message.answer("❌ Ввод промокода отменён.", reply_markup=bottom_menu)
        return

    code = message.text.strip().upper()
    promo = get_promocode(code)
    if not promo:
        await message.answer("❌ *Неверный промокод.* Попробуйте ещё раз.", parse_mode="Markdown")
        return

    code_text, days, used_by, used_at = promo
    if used_by is not None:
        await message.answer("❌ *Этот промокод уже был использован.*", parse_mode="Markdown")
        return

    tg_id = message.from_user.id
    user = get_user(tg_id)
    now = int(time.time())
    
    if user and user[1] and user[1] > now:
        new_expire = user[1] + days * 86400
        add_or_update_user(tg_id, user[0], new_expire, subscription_link=user[6])
        expire_display = format_datetime(new_expire)
    else:
        # Берём новую ссылку из пула
        link_data = get_free_link()
        if not link_data:
            await message.answer("❌ *Нет свободных ссылок.* Обратитесь к администратору.", parse_mode="Markdown")
            await state.clear()
            return
        link_id, link = link_data
        mark_link_used(link_id, tg_id)
        expire_ts = now + days * 86400
        add_or_update_user(tg_id, "promo", expire_ts, subscription_link=link)
        expire_display = format_datetime(expire_ts)

    use_promocode(code, tg_id)
    await state.clear()
    await message.answer(
        f"✅ *Промокод активирован!*\n\n"
        f"▸ Добавлено `{days}` дней.\n"
        f"▸ Новая дата окончания: `{expire_display}`",
        parse_mode="Markdown",
        reply_markup=bottom_menu
    )

# ---------------------------------- ДРУГИЕ КНОПКИ ----------------------------------
@dp.message(F.text == "📢 Канал")
async def channel_cmd(message: types.Message):
    await message.answer(
        f"📢 *Наш канал:*\n{CHANNEL_ID}\n\n"
        "Подписывайтесь, чтобы быть в курсе новостей и акций!",
        parse_mode="Markdown"
    )

@dp.message(F.text == "❓ Поддержка")
async def support_cmd(message: types.Message):
    await message.answer(
        f"❓ *Поддержка*\n\n"
        f"По всем вопросам пишите: {PAYMENT_CONTACT}\n"
        "Мы ответим в ближайшее время.",
        parse_mode="Markdown"
    )

@dp.message(F.text == "📜 Соглашение")
async def agreement_cmd(message: types.Message):
    await message.answer(
        "📜 *Пользовательское соглашение*\n\n"
        "Ознакомьтесь с полным текстом соглашения по ссылке ниже:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📄 Открыть соглашение", url="https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19")]
        ])
    )

@dp.message(F.text == "ℹ️ Политика")
async def policy_cmd(message: types.Message):
    await message.answer(
        "ℹ️ *Политика конфиденциальности*\n\n"
        "Ознакомьтесь с полным текстом политики по ссылке ниже:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📄 Открыть политику", url="https://telegra.ph/Politika-konfidencialnosti-06-11-43")]
        ])
    )

# ---------------------------------- АДМИН-ПАНЕЛЬ: УПРАВЛЕНИЕ ССЫЛКАМИ ----------------------------------
@dp.message(F.text == "📦 Управление ссылками")
async def manage_links(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить ссылки")],
            [KeyboardButton(text="📋 Список ссылок")],
            [KeyboardButton(text="🗑️ Удалить ссылку")],
            [KeyboardButton(text="🔙 Назад в админку")]
        ],
        resize_keyboard=True
    )
    await message.answer("📦 *Управление пулом ссылок*\nВыберите действие:", parse_mode="Markdown", reply_markup=kb)

# Добавление ссылок (поддерживает текст и файл)
@dp.message(F.text == "➕ Добавить ссылки")
async def add_links_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_link_input)
    await message.answer(
        "✏️ Введите ссылки (каждую с новой строки) **или отправьте текстовый файл (.txt)**.\n"
        "Поддерживаются только vless://, vmess://, trojan://\n"
        "Для отмены введите /cancel",
        parse_mode="Markdown"
    )

# Обработка загруженного файла
@dp.message(AdminStates.waiting_for_link_input, F.document)
async def add_links_from_file(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    document = message.document
    if document.mime_type != "text/plain":
        await message.answer("❌ Пожалуйста, отправьте текстовый файл (.txt).")
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
    await message.answer(
        f"✅ *Добавлено:* `{added}` ссылок\n"
        f"⚠️ *Пропущено:* `{skipped}` (неверный формат или дубликат)",
        parse_mode="Markdown",
        reply_markup=admin_keyboard
    )

# Обработка текстового ввода
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
    await message.answer(
        f"✅ *Добавлено:* `{added}` ссылок\n"
        f"⚠️ *Пропущено:* `{skipped}` (неверный формат или дубликат)",
        parse_mode="Markdown",
        reply_markup=admin_keyboard
    )

# Список ссылок
@dp.message(F.text == "📋 Список ссылок")
async def list_links(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    links = get_all_pool_links()
    if not links:
        await message.answer("📭 *Пул ссылок пуст.*", parse_mode="Markdown", reply_markup=admin_keyboard)
        return
    text = "📋 *Список ссылок в пуле:*\n\n"
    for link_id, link, used, used_by in links:
        status = "❌ Использована" if used else "✅ Свободна"
        used_info = f" (пользователь {used_by})" if used_by else ""
        text += f"ID `{link_id}`: `{link[:50]}...` — {status}{used_info}\n"
    await message.answer(text, parse_mode="Markdown", reply_markup=admin_keyboard)

# Удаление ссылки
@dp.message(F.text == "🗑️ Удалить ссылку")
async def delete_link_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_link_delete)
    await message.answer(
        "✏️ Введите ID ссылки, которую хотите удалить (из списка).\n"
        "Для отмены введите /cancel",
        parse_mode="Markdown"
    )

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
        await message.answer(f"✅ *Ссылка с ID `{link_id}` удалена.*", parse_mode="Markdown", reply_markup=admin_keyboard)
    except ValueError:
        await message.answer("❌ *Неверный ID.* Введите число.", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ *Ошибка:* {e}", parse_mode="Markdown")
    await state.clear()

@dp.message(F.text == "🔙 Назад в админку")
async def back_to_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("Возврат в админ-панель.", reply_markup=admin_keyboard)

# ---------------------------------- АДМИН-ПАНЕЛЬ (остальное) ----------------------------------
@dp.message(F.text == "🔙 Выйти из админ-панели")
async def admin_exit(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("👋 Выход из админ-панели.", reply_markup=ReplyKeyboardRemove())
    await message.answer("📌 *Главное меню*", parse_mode="Markdown", reply_markup=main_menu)
    await message.answer("👇 *Нижнее меню*", parse_mode="Markdown", reply_markup=bottom_menu)

@dp.message(F.text == "👥 Список пользователей")
async def admin_list_users(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    users = get_all_active_users()
    if not users:
        await message.answer("📭 *Активных пользователей нет.*", parse_mode="Markdown")
        return
    text = "👥 *Активные пользователи:*\n\n"
    for tg_id, expire_ts in users:
        user = get_user(tg_id)
        if user:
            tariff = user[0] or "неизвестно"
            time_left = format_time_left(expire_ts)
            text += f"▸ ID `{tg_id}` – {tariff}, осталось `{time_left}`\n"
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
        f"📊 *Статистика {VPN_NAME}*\n\n"
        f"▸ Всего записей: `{total}`\n"
        f"▸ Активных подписок: `{active}`\n"
        f"▸ Бесплатных: `{free_count}`\n"
        f"▸ Платных: `{paid_count}`\n"
        f"▸ По промокодам: `{promo_count}`",
        parse_mode="Markdown"
    )

# ---------------------------- АКТИВАЦИЯ ПОДПИСКИ (гибкое количество дней) ----------------------------
@dp.message(F.text == "✅ Активировать подписку")
async def admin_activate_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_user_id)
    await message.answer(
        "✏️ Введите *Telegram ID* пользователя (только число):",
        parse_mode="Markdown"
    )

@dp.message(AdminStates.waiting_for_user_id)
async def admin_activate_get_id(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        tg_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ *Неверный формат.* Введите число.", parse_mode="Markdown")
        return

    await state.update_data(tg_id=tg_id)
    await state.set_state(AdminStates.waiting_for_days)
    await message.answer(
        "✏️ Введите *количество дней* подписки (например, `30`, `7`, `1`):",
        parse_mode="Markdown"
    )

@dp.message(AdminStates.waiting_for_days)
async def admin_activate_get_days(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ *Неверный формат.* Введите положительное число.", parse_mode="Markdown")
        return

    data = await state.get_data()
    tg_id = data['tg_id']
    await state.clear()

    user = get_user(tg_id)
    if user is not None and user[6]:
        delete_user(tg_id)

    link_data = get_free_link()
    if not link_data:
        await message.answer("❌ *Нет свободных ссылок.* Пополните пул через «Управление ссылками».", parse_mode="Markdown")
        await state.clear()
        return
    link_id, link = link_data
    mark_link_used(link_id, tg_id)

    expire_ts = int(time.time()) + days * 86400
    add_or_update_user(tg_id, "paid", expire_ts, subscription_link=link)

    await bot.send_message(
        tg_id,
        f"🎉 *Ваша подписка активирована администратором!*\n\n"
        f"▸ Срок: `{days}` дней\n"
        f"▸ Действует до: `{format_datetime(expire_ts)}`\n"
        f"🔗 *Ваша ссылка:*\n`{link}`\n\n"
        "📌 Скопируйте ссылку и вставьте в V2RayTun / Happ.",
        parse_mode="Markdown"
    )
    await message.answer(f"✅ *Подписка для `{tg_id}` активирована на {days} дней.*", parse_mode="Markdown")

# ---------------------------- СОЗДАНИЕ ПРОМОКОДА ----------------------------
@dp.message(F.text == "🎫 Создать промокод")
async def admin_create_promo_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_promo_days)
    await message.answer(
        "✏️ Введите *количество дней*, которое даёт промокод (например, `3`, `7`):",
        parse_mode="Markdown"
    )

@dp.message(AdminStates.waiting_for_promo_days)
async def admin_create_promo_days(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ *Неверный формат.* Введите положительное число.", parse_mode="Markdown")
        return

    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    add_promocode(code, days)

    await state.clear()
    await message.answer(
        f"✅ *Промокод создан!*\n\n"
        f"▸ Код: `{code}`\n"
        f"▸ Даёт: `{days}` дней подписки\n\n"
        "📋 Вы можете отправить этот код пользователям.",
        parse_mode="Markdown"
    )

# ---------------------------- СПИСОК ПРОМОКОДОВ ----------------------------
@dp.message(F.text == "📋 Список промокодов")
async def admin_list_promocodes(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    promos = get_all_promocodes()
    if not promos:
        await message.answer("📭 *Промокодов пока нет.*", parse_mode="Markdown")
        return
    text = "📋 *Список промокодов:*\n\n"
    for code, days, used_by, created_at, used_at in promos:
        status = "✅ Использован" if used_by else "🟢 Активен"
        used_info = f" (использовал {used_by})" if used_by else ""
        text += f"▸ `{code}` – {days} дней – {status}{used_info}\n"
    await message.answer(text, parse_mode="Markdown")

# ---------------------------- РАССЫЛКА ----------------------------
@dp.message(F.text == "📨 Сделать рассылку")
async def admin_broadcast_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_broadcast_text)
    await message.answer(
        "✏️ *Введите текст рассылки.*\n"
        "Можно использовать Markdown (жирный, курсив, ссылки).\n\n"
        "Для отмены просто нажмите «Выйти из админ-панели».",
        parse_mode="Markdown"
    )

@dp.message(AdminStates.waiting_for_broadcast_text)
async def admin_broadcast_get_text(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    text = message.text
    if not text:
        await message.answer("❌ Текст не может быть пустым. Попробуйте снова.")
        return
    await state.update_data(broadcast_text=text)
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast_confirm")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="broadcast_cancel")]
    ])
    await message.answer(
        "📨 *Предпросмотр рассылки:*\n\n" + text + "\n\n"
        "Отправить это сообщение всем пользователям?",
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
        await callback.message.edit_text("❌ Текст не найден. Попробуйте заново.")
        await state.clear()
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT tg_id FROM users')
    rows = c.fetchall()
    conn.close()

    if not rows:
        await callback.message.edit_text("📭 *Нет пользователей для рассылки.*")
        await state.clear()
        return

    sent = 0
    failed = 0
    for (tg_id,) in rows:
        try:
            await bot.send_message(tg_id, text, parse_mode="Markdown")
            sent += 1
            await asyncio.sleep(0.1)
        except Exception:
            failed += 1

    await callback.message.edit_text(
        f"✅ *Рассылка завершена!*\n\n"
        f"▸ Отправлено: `{sent}`\n"
        f"▸ Не удалось: `{failed}`"
    )
    await state.clear()

@dp.callback_query(F.data == "broadcast_cancel")
async def admin_broadcast_cancel(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Доступ запрещён.", show_alert=True)
        return
    await callback.message.edit_text("❌ Рассылка отменена.")
    await state.clear()

# ---------------------------------- ЗАПУСК ----------------------------------
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
