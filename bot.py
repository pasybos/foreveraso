import asyncio
import time
import os
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, FSInputFile, LabeledPrice, PreCheckoutQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from config import (BOT_TOKEN, ADMIN_IDS, FREE_HOURS, VPN_NAME, DB_PATH,
                    CHANNEL_ID, PAYMENT_CONTACT, IMAGE_PATH, BOT_USERNAME,
                    TARIFFS, ALL_POOLS, POOL_LABELS)
from database import init_db, get_user, add_or_update_user, delete_user, get_all_active_users
from database import add_promocode, get_promocode, use_promocode, get_all_promocodes
from database import add_link_to_pool, get_free_link_from_pool, mark_link_used_in_pool
from database import get_all_links_from_pool, delete_link_from_pool
from database import get_setting, set_setting
from utils import format_time_left, format_datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ------------------------- состояния -------------------------
class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_tariff = State()
    waiting_for_ref_user_id = State()
    waiting_for_promo_days = State()
    waiting_for_broadcast_text = State()
    waiting_for_broadcast_confirm = State()
    waiting_for_link_input = State()
    waiting_for_link_delete = State()
    waiting_for_ref_settings = State()
    managing_pool = State()

class UserStates(StatesGroup):
    waiting_for_promo_code = State()

# ------------------------- клавиатуры -------------------------

main_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📖 Инструкция", callback_data="instructions")],
    [InlineKeyboardButton(text="🚀 Получить подписку", callback_data="get_free")],
    [InlineKeyboardButton(text="💰 Прайс и оплата", callback_data="buy_menu")],
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
        [KeyboardButton(text="📦 Пул: Бесплатные")],
        [KeyboardButton(text="📦 Пул: Реферальные")],
        [KeyboardButton(text="📦 Пул: Неделя")],
        [KeyboardButton(text="📦 Пул: Месяц")],
        [KeyboardButton(text="📦 Пул: Полгода")],
        [KeyboardButton(text="📦 Пул: Год")],
        [KeyboardButton(text="📦 Пул: Навсегда")],
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

# ------------------------- проверка подписки -------------------------
async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

# ------------------------- вспомогательная: подбор пула по дням -------------------------
def get_pool_for_days(days: int) -> str:
    sorted_tariffs = sorted(TARIFFS.items(), key=lambda x: x[1]['days'])
    for key, tariff in sorted_tariffs:
        if tariff['days'] >= days:
            return tariff['pool']
    return 'forever'

# ------------------------- /start -------------------------
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
        "💰 Или купите подписку через «Прайс и оплата»\n"
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

# ------------------------- /admin -------------------------
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

# ------------------------- реферальная система -------------------------
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
                           current_link=referrer[6],
                           ref_link=referrer[7])
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
    link_data = get_free_link_from_pool("ref")
    if not link_data:
        logger.warning(f"Нет свободных реферальных ссылок для {tg_id}")
        for admin_id in ADMIN_IDS:
            await bot.send_message(admin_id, f"⚠️ Закончились реферальные ссылки! Пользователь {tg_id} не получил бонус.")
        return
    link_id, link = link_data
    mark_link_used_in_pool("ref", link_id, tg_id)
    expire_ts = int(time.time()) + bonus_days * 86400
    add_or_update_user(tg_id, "ref_bonus", expire_ts, current_link=link)
    await bot.send_message(
        tg_id,
        f"🎉 *Поздравляем! Вы привели {get_setting('ref_required')} пользователей!*\n"
        f"Вы получили бонусную подписку на {bonus_days} дней!\n"
        f"🔗 Ваша ссылка:\n`{link}`\n\n"
        "📌 Вставьте её в V2RayTun / Happ.",
        parse_mode="Markdown"
    )

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

    ref_link = user[7] if user else None
    if not ref_link:
        ref_link = f"ref_{tg_id}"
        add_or_update_user(tg_id, user[0], user[1],
                           last_free=user[3] if user else 0,
                           used_free=user[4] if user else 0,
                           ref_count=ref_count,
                           referrer_id=user[5] if user else None,
                           current_link=user[6] if user else None,
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

# ------------------------- бесплатная подписка (пул free) -------------------------
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

    link_data = get_free_link_from_pool("free")
    if not link_data:
        await callback.message.answer(
            "😕 *Нет свободных ссылок.* Обратитесь к администратору.",
            parse_mode="Markdown"
        )
        return
    link_id, link = link_data
    mark_link_used_in_pool("free", link_id, tg_id)
    expire_ts = int(time.time()) + FREE_HOURS * 3600
    add_or_update_user(tg_id, "free", expire_ts, used_free=1, current_link=link)
    await callback.message.answer(
        f"✅ *Бесплатная подписка активирована!*\n\n"
        f"▸ Действует до: {format_datetime(expire_ts)}\n"
        f"🔗 Ваша ссылка:\n`{link}`\n\n"
        "📌 Вставьте её в V2RayTun / Happ.",
        parse_mode="Markdown",
        reply_markup=back_button
    )

# ------------------------- ПРАЙС И ОПЛАТА -------------------------
@dp.callback_query(F.data == "buy_menu")
async def buy_menu(callback: types.CallbackQuery):
    text = "💎 *Наши тарифы:*\n\n"
    for key, tariff in TARIFFS.items():
        if key in ("free", "ref"):
            continue
        name = tariff["label"]
        text += f"▸ *{name}* — {tariff['days']} дн.\n"
        text += f"  ⭐ {tariff['price_stars']} звёзд / 💳 {tariff['price_rub']}\n\n"
    text += "Выберите способ оплаты:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Оплатить звёздами", callback_data="buy_stars_menu")],
        [InlineKeyboardButton(text="💳 Оплатить рублями (через администратора)", callback_data="buy_manual")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ])
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "buy_stars_menu")
async def buy_stars_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for key, tariff in TARIFFS.items():
        if key in ("free", "ref"):
            continue
        name = tariff["label"]
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{name} ({tariff['days']} дн.) — {tariff['price_stars']} ⭐",
                callback_data=f"stars_{key}"
            )
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="buy_menu")])
    await callback.message.edit_text("⭐ *Выберите тариф для оплаты звёздами:*", parse_mode="Markdown", reply_markup=kb)
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
    tariff_name = tariff_data["label"]
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
    pool = tariff_data["pool"]

    link_data = get_free_link_from_pool(pool)
    if not link_data:
        await message.answer("❌ Нет свободных ссылок для этого тарифа. Администратор будет уведомлён.")
        for admin_id in ADMIN_IDS:
            await bot.send_message(admin_id, f"⚠️ Закончились ссылки в пуле {pool}! Пользователь {user_id} оплатил, но не получил подписку.")
        return
    link_id, link = link_data
    mark_link_used_in_pool(pool, link_id, user_id)
    expire_ts = int(time.time()) + days * 86400
    add_or_update_user(user_id, f"paid_{tariff_key}", expire_ts, current_link=link)

    await message.answer(
        f"✅ *Оплата прошла успешно!*\n\n"
        f"▸ Подписка активирована на {days} дней.\n"
        f"▸ Действует до: {format_datetime(expire_ts)}\n"
        f"🔗 Ваша ссылка:\n`{link}`\n\n"
        "📌 Вставьте её в V2RayTun / Happ.",
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "buy_manual")
async def buy_manual(callback: types.CallbackQuery):
    text = "💳 *Оплата рублями через администратора*\n\n"
    text += "Наши тарифы:\n"
    for key, tariff in TARIFFS.items():
        if key in ("free", "ref"):
            continue
        text += f"▸ *{tariff['label']}* — {tariff['days']} дн., {tariff['price_rub']}\n"
    text += "\nДля покупки свяжитесь с администратором:\n"
    text += f"📩 **@{PAYMENT_CONTACT}**\n\n"
    text += "После оплаты администратор активирует подписку вручную."
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="buy_menu")]
    ]))
    await callback.answer()

# ------------------------- АДМИН: АКТИВАЦИЯ ПОДПИСКИ (ручная выдача) -------------------------
@dp.message(F.text == "✅ Активировать подписку")
async def activate_sub_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_user_id)
    await message.answer("✏️ Введите ID пользователя (число). Для отмены /cancel", parse_mode="Markdown")

@dp.message(AdminStates.waiting_for_user_id)
async def activate_sub_get_user(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=admin_keyboard)
        return
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите корректный ID (число).")
        return
    await state.update_data(user_id=user_id)
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Неделя (7д)")],
            [KeyboardButton(text="Месяц (30д)")],
            [KeyboardButton(text="Полгода (180д)")],
            [KeyboardButton(text="Год (365д)")],
            [KeyboardButton(text="Навсегда (3650д)")],
            [KeyboardButton(text="🔙 Отмена")]
        ],
        resize_keyboard=True
    )
    await state.set_state(AdminStates.waiting_for_tariff)
    await message.answer("Выберите тариф для активации:", reply_markup=kb)

@dp.message(AdminStates.waiting_for_tariff)
async def activate_sub_choose_tariff(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if message.text == "🔙 Отмена" or message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=admin_keyboard)
        return

    tariff_map = {
        "Неделя (7д)": "week",
        "Месяц (30д)": "month",
        "Полгода (180д)": "halfyear",
        "Год (365д)": "year",
        "Навсегда (3650д)": "forever"
    }
    tariff_key = tariff_map.get(message.text)
    if not tariff_key:
        await message.answer("❌ Неизвестный тариф. Выберите из кнопок.")
        return

    tariff_data = TARIFFS.get(tariff_key)
    if not tariff_data:
        await message.answer("❌ Тариф не найден.")
        return

    data = await state.get_data()
    user_id = data.get("user_id")
    if not user_id:
        await message.answer("❌ Ошибка: пользователь не определён.")
        await state.clear()
        return

    days = tariff_data["days"]
    pool = tariff_data["pool"]
    link_data = get_free_link_from_pool(pool)
    if not link_data:
        await message.answer(f"❌ В пуле {POOL_LABELS[pool]} нет свободных ссылок. Пополните пул.", reply_markup=admin_keyboard)
        await state.clear()
        return
    link_id, link = link_data
    mark_link_used_in_pool(pool, link_id, user_id)
    expire_ts = int(time.time()) + days * 86400
    add_or_update_user(user_id, f"admin_{tariff_key}", expire_ts, current_link=link)

    try:
        await bot.send_message(
            user_id,
            f"🎉 *Администратор активировал подписку!*\n\n"
            f"▸ Тариф: {tariff_data['label']}\n"
            f"▸ Срок: {days} дней\n"
            f"▸ Действует до: {format_datetime(expire_ts)}\n"
            f"🔗 Ваша ссылка:\n`{link}`\n\n"
            "📌 Вставьте её в V2RayTun / Happ.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

    await message.answer(
        f"✅ Подписка для `{user_id}` активирована на {days} дней (тариф {tariff_data['label']}).",
        parse_mode="Markdown",
        reply_markup=admin_keyboard
    )
    await state.clear()

# ------------------------- АДМИН: АКТИВАЦИЯ РЕФЕРАЛЬНОЙ ПОДПИСКИ (ручная) -------------------------
@dp.message(F.text == "✅ Активировать реферальную подписку")
async def activate_ref_sub_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_ref_user_id)
    await message.answer("✏️ Введите ID пользователя для активации реферальной подписки (14 дней). Для отмены /cancel", parse_mode="Markdown")

@dp.message(AdminStates.waiting_for_ref_user_id)
async def activate_ref_sub_process(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=admin_keyboard)
        return
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите корректный ID (число).")
        return

    days = 14
    pool = "ref"
    link_data = get_free_link_from_pool(pool)
    if not link_data:
        await message.answer(f"❌ В пуле {POOL_LABELS[pool]} нет свободных ссылок. Пополните пул.", reply_markup=admin_keyboard)
        await state.clear()
        return
    link_id, link = link_data
    mark_link_used_in_pool(pool, link_id, user_id)
    expire_ts = int(time.time()) + days * 86400
    add_or_update_user(user_id, "admin_ref", expire_ts, current_link=link)

    try:
        await bot.send_message(
            user_id,
            f"🎉 *Администратор активировал реферальную подписку!*\n\n"
            f"▸ Срок: {days} дней\n"
            f"▸ Действует до: {format_datetime(expire_ts)}\n"
            f"🔗 Ваша ссылка:\n`{link}`\n\n"
            "📌 Вставьте её в V2RayTun / Happ.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

    await message.answer(
        f"✅ Реферальная подписка для `{user_id}` активирована на {days} дней.",
        parse_mode="Markdown",
        reply_markup=admin_keyboard
    )
    await state.clear()

# ------------------------- /give_sub (командная выдача) -------------------------
@dp.message(Command("give_sub"))
async def give_sub_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет прав.")
        return
    args = message.text.split()
    if len(args) < 3:
        await message.answer("❌ Использование:\n"
                             "`/give_sub <ID> <дни>`\n"
                             "`/give_sub <ID> <тариф>` (week, month, halfyear, year, forever)",
                             parse_mode="Markdown")
        return
    try:
        tg_id = int(args[1])
    except ValueError:
        await message.answer("❌ ID должен быть числом.")
        return

    arg2 = args[2].lower()
    if arg2 in TARIFFS:
        tariff_key = arg2
        tariff_data = TARIFFS[tariff_key]
        days = tariff_data["days"]
        pool = tariff_data["pool"]
    else:
        try:
            days = int(arg2)
            pool = get_pool_for_days(days)
        except ValueError:
            await message.answer("❌ Второй аргумент должен быть числом (дни) или названием тарифа.")
            return

    link_data = get_free_link_from_pool(pool)
    if not link_data:
        await message.answer(f"❌ В пуле {POOL_LABELS[pool]} нет свободных ссылок.", reply_markup=admin_keyboard)
        return
    link_id, link = link_data
    mark_link_used_in_pool(pool, link_id, tg_id)
    expire_ts = int(time.time()) + days * 86400
    add_or_update_user(tg_id, f"give_{days}d", expire_ts, current_link=link)

    try:
        await bot.send_message(
            tg_id,
            f"🎉 *Администратор активировал подписку!*\n\n"
            f"▸ Срок: {days} дней\n"
            f"▸ Действует до: {format_datetime(expire_ts)}\n"
            f"🔗 Ваша ссылка:\n`{link}`\n\n"
            "📌 Вставьте её в V2RayTun / Happ.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение пользователю {tg_id}: {e}")

    await message.answer(
        f"✅ Подписка для `{tg_id}` активирована на {days} дней (пул {POOL_LABELS[pool]}).",
        parse_mode="Markdown",
        reply_markup=admin_keyboard
    )

# ------------------------- АДМИН: УПРАВЛЕНИЕ ПУЛАМИ (обобщённое) -------------------------
# При нажатии на кнопку "📦 Пул: ..." устанавливаем текущий пул и показываем меню управления
@dp.message(F.text.startswith("📦 Пул:"))
async def manage_pool_menu(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    pool_name = message.text.replace("📦 Пул: ", "").strip()
    pool_key = None
    for key, label in POOL_LABELS.items():
        if label == pool_name:
            pool_key = key
            break
    if not pool_key:
        await message.answer("❌ Неизвестный пул.")
        return

    await state.set_state(AdminStates.managing_pool)
    await state.update_data(pool=pool_key)

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить ссылки")],
            [KeyboardButton(text="📋 Список ссылок")],
            [KeyboardButton(text="🗑️ Удалить ссылку")],
            [KeyboardButton(text="🔙 Назад в админку")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        f"📦 *Управление пулом:* {POOL_LABELS[pool_key]}\n"
        "Выберите действие:",
        parse_mode="Markdown",
        reply_markup=kb
    )

# Обработчик добавления ссылок (для текущего пула)
@dp.message(AdminStates.managing_pool, F.text == "➕ Добавить ссылки")
async def add_links_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_link_input)
    await message.answer(
        "✏️ Введите ссылки (vless://, vmess://, trojan://) — каждая с новой строки, или отправьте .txt файл.\n"
        "Для отмены введите /cancel",
        parse_mode="Markdown"
    )

@dp.message(AdminStates.waiting_for_link_input, F.document)
async def add_links_from_file(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    data = await state.get_data()
    pool = data.get("pool")
    if not pool:
        await message.answer("❌ Ошибка: пул не определён.")
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
                add_link_to_pool(pool, link)
                added += 1
            except:
                skipped += 1
        else:
            skipped += 1
    await state.set_state(AdminStates.managing_pool)
    await message.answer(
        f"✅ Добавлено {added} ссылок в пул {POOL_LABELS[pool]}, пропущено {skipped} (неверный формат/дубликат).",
        reply_markup=admin_keyboard
    )

@dp.message(AdminStates.waiting_for_link_input, F.text)
async def add_links_process(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=admin_keyboard)
        return
    data = await state.get_data()
    pool = data.get("pool")
    if not pool:
        await message.answer("❌ Ошибка: пул не определён.")
        return

    links = message.text.strip().splitlines()
    added = 0
    skipped = 0
    for link in links:
        link = link.strip()
        if link.startswith(("vless://", "vmess://", "trojan://")):
            try:
                add_link_to_pool(pool, link)
                added += 1
            except:
                skipped += 1
        else:
            skipped += 1
    await state.set_state(AdminStates.managing_pool)
    await message.answer(
        f"✅ Добавлено {added} ссылок в пул {POOL_LABELS[pool]}, пропущено {skipped} (неверный формат/дубликат).",
        reply_markup=admin_keyboard
    )

# Список ссылок текущего пула
@dp.message(AdminStates.managing_pool, F.text == "📋 Список ссылок")
async def list_links_pool(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    data = await state.get_data()
    pool = data.get("pool")
    if not pool:
        await message.answer("❌ Ошибка: пул не определён.")
        return
    links = get_all_links_from_pool(pool)
    if not links:
        await message.answer(f"📭 Пул {POOL_LABELS[pool]} пуст.", reply_markup=admin_keyboard)
        return
    text = f"📋 *Список ссылок в пуле {POOL_LABELS[pool]}:*\n\n"
    for link_id, link, used, used_by in links:
        status = "❌ Использована" if used else "✅ Свободна"
        used_info = f" (пользователь {used_by})" if used_by else ""
        text += f"ID `{link_id}`: `{link[:50]}...` — {status}{used_info}\n"
    await message.answer(text, parse_mode="Markdown", reply_markup=admin_keyboard)

# Удаление ссылки из текущего пула
@dp.message(AdminStates.managing_pool, F.text == "🗑️ Удалить ссылку")
async def delete_link_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
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
    data = await state.get_data()
    pool = data.get("pool")
    if not pool:
        await message.answer("❌ Ошибка: пул не определён.")
        return
    try:
        link_id = int(message.text.strip())
        delete_link_from_pool(pool, link_id)
        await message.answer(f"✅ Ссылка с ID `{link_id}` удалена из пула {POOL_LABELS[pool]}.", parse_mode="Markdown", reply_markup=admin_keyboard)
    except ValueError:
        await message.answer("❌ Неверный ID, введите число.", reply_markup=admin_keyboard)
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=admin_keyboard)
    await state.set_state(AdminStates.managing_pool)

# ------------------------- АДМИН: РЕФЕРАЛЬНЫЕ НАСТРОЙКИ -------------------------
@dp.message(F.text == "⚙️ Реферальные настройки")
async def ref_settings_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_ref_settings)
    current_required = get_setting("ref_required") or 5
    current_bonus = get_setting("ref_bonus_days") or 14
    await message.answer(
        f"⚙️ *Текущие настройки реферальной системы:*\n"
        f"▸ Необходимое кол-во рефералов: {current_required}\n"
        f"▸ Бонусных дней: {current_bonus}\n\n"
        "Введите новые значения через пробел:\n"
        "`<кол-во рефералов> <бонусные дни>`\n"
        "Например: `5 14`\n\n"
        "Для отмены введите /cancel",
        parse_mode="Markdown"
    )

@dp.message(AdminStates.waiting_for_ref_settings)
async def ref_settings_process(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=admin_keyboard)
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❌ Введите два числа через пробел.")
        return
    try:
        required = int(parts[0])
        bonus_days = int(parts[1])
        if required < 1 or bonus_days < 1:
            await message.answer("❌ Значения должны быть положительными числами.")
            return
    except ValueError:
        await message.answer("❌ Введите корректные числа.")
        return
    set_setting("ref_required", str(required))
    set_setting("ref_bonus_days", str(bonus_days))
    await state.clear()
    await message.answer(
        f"✅ Настройки обновлены:\n"
        f"▸ Рефералов для бонуса: {required}\n"
        f"▸ Бонусных дней: {bonus_days}",
        reply_markup=admin_keyboard
    )

# ------------------------- АДМИН: ПРОМОКОДЫ -------------------------
@dp.message(F.text == "🎫 Создать промокод")
async def create_promo_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_promo_days)
    await message.answer("✏️ Введите количество дней для промокода (число). Для отмены /cancel", parse_mode="Markdown")

@dp.message(AdminStates.waiting_for_promo_days)
async def create_promo_process(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=admin_keyboard)
        return
    try:
        days = int(message.text.strip())
        if days <= 0:
            await message.answer("❌ Дни должны быть положительным числом.")
            return
    except ValueError:
        await message.answer("❌ Введите число.")
        return
    # Генерация кода
    import random, string
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    add_promocode(code, days)
    await state.clear()
    await message.answer(
        f"✅ Промокод создан:\n`{code}`\n\n"
        f"Активирует подписку на {days} дней.",
        parse_mode="Markdown",
        reply_markup=admin_keyboard
    )

@dp.message(F.text == "📋 Список промокодов")
async def list_promocodes(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    promos = get_all_promocodes()
    if not promos:
        await message.answer("📭 Нет промокодов.", reply_markup=admin_keyboard)
        return
    text = "📋 *Список промокодов:*\n\n"
    for code, days, used_by, created_at, used_at in promos:
        status = "❌ Использован" if used_by else "✅ Активен"
        used_info = f" (пользователь {used_by})" if used_by else ""
        text += f"`{code}` — {days} дн., {status}{used_info}\n"
    await message.answer(text, parse_mode="Markdown", reply_markup=admin_keyboard)

# ------------------------- АДМИН: РАССЫЛКА -------------------------
@dp.message(F.text == "📨 Сделать рассылку")
async def broadcast_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_broadcast_text)
    await message.answer("✏️ Введите текст для рассылки. Для отмены /cancel", parse_mode="Markdown")

@dp.message(AdminStates.waiting_for_broadcast_text)
async def broadcast_process(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено.", reply_markup=admin_keyboard)
        return
    text = message.text
    await state.update_data(broadcast_text=text)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="broadcast_confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel")]
    ])
    await state.set_state(AdminStates.waiting_for_broadcast_confirm)
    await message.answer(
        f"📨 *Текст рассылки:*\n\n{text}\n\nПодтвердите отправку:",
        parse_mode="Markdown",
        reply_markup=kb
    )

@dp.callback_query(F.data == "broadcast_confirm", AdminStates.waiting_for_broadcast_confirm)
async def broadcast_confirm(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    data = await state.get_data()
    text = data.get("broadcast_text")
    if not text:
        await callback.answer("Ошибка: нет текста", show_alert=True)
        return
    users = get_all_active_users()
    sent = 0
    for tg_id, _ in users:
        try:
            await bot.send_message(tg_id, text, parse_mode="Markdown")
            sent += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await callback.message.edit_text(f"✅ Рассылка завершена. Отправлено {sent} пользователям.")
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "broadcast_cancel", AdminStates.waiting_for_broadcast_confirm)
async def broadcast_cancel(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Нет прав", show_alert=True)
        return
    await callback.message.edit_text("❌ Рассылка отменена.")
    await state.clear()
    await callback.answer()

# ------------------------- АДМИН: СТАТИСТИКА -------------------------
@dp.message(F.text == "📊 Статистика")
async def stats(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    users = get_all_active_users()
    active = len(users)
    total = len(get_all_promocodes())  # не совсем, но для примера
    # Получаем количество всех пользователей
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users')
    total_users = c.fetchone()[0]
    conn.close()
    await message.answer(
        f"📊 *Статистика бота:*\n\n"
        f"▸ Всего пользователей: {total_users}\n"
        f"▸ Активных подписок: {active}\n"
        f"▸ Промокодов создано: {len(get_all_promocodes())}\n"
        f"▸ Пул бесплатных: {len(get_all_links_from_pool('free'))} ссылок\n"
        f"▸ Пул реферальных: {len(get_all_links_from_pool('ref'))} ссылок\n"
        f"▸ Пул неделя: {len(get_all_links_from_pool('week'))} ссылок\n"
        f"▸ Пул месяц: {len(get_all_links_from_pool('month'))} ссылок\n"
        f"▸ Пул полгода: {len(get_all_links_from_pool('halfyear'))} ссылок\n"
        f"▸ Пул год: {len(get_all_links_from_pool('year'))} ссылок\n"
        f"▸ Пул навсегда: {len(get_all_links_from_pool('forever'))} ссылок",
        parse_mode="Markdown",
        reply_markup=admin_keyboard
    )

# ------------------------- АДМИН: СПИСОК ПОЛЬЗОВАТЕЛЕЙ -------------------------
@dp.message(F.text == "👥 Список пользователей")
async def list_users(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT tg_id, tariff, expire_time FROM users ORDER BY tg_id')
    rows = c.fetchall()
    conn.close()
    if not rows:
        await message.answer("📭 Нет пользователей.", reply_markup=admin_keyboard)
        return
    text = "👥 *Список пользователей:*\n\n"
    for tg_id, tariff, expire in rows:
        status = "✅ Активен" if expire and expire > int(time.time()) else "❌ Неактивен"
        expire_str = format_datetime(expire) if expire else "—"
        text += f"ID: `{tg_id}` | Тариф: {tariff or '—'} | До: {expire_str} | {status}\n"
    await message.answer(text, parse_mode="Markdown", reply_markup=admin_keyboard)

# ------------------------- АДМИН: ВЫХОД -------------------------
@dp.message(F.text == "🔙 Выйти из админ-панели")
async def exit_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("👋 Вы вышли из админ-панели.", reply_markup=bottom_menu)

# ------------------------- НИЖНЕЕ МЕНЮ (профиль, промокод, канал и т.д.) -------------------------
@dp.message(F.text == "👤 Профиль")
async def profile(message: types.Message):
    tg_id = message.from_user.id
    user = get_user(tg_id)
    if not user:
        await message.answer("❌ Вы не зарегистрированы. Напишите /start.")
        return
    tariff = user[0] or "Нет"
    expire = user[1]
    status = "✅ Активна" if expire and expire > int(time.time()) else "❌ Неактивна"
    time_left = format_time_left(expire) if expire and expire > int(time.time()) else "—"
    ref_count = user[4]
    await message.answer(
        f"👤 *Ваш профиль*\n\n"
        f"▸ Тариф: {tariff}\n"
        f"▸ Статус: {status}\n"
        f"▸ Действует до: {format_datetime(expire) if expire else '—'}\n"
        f"▸ Осталось: {time_left}\n"
        f"▸ Рефералов: {ref_count}",
        parse_mode="Markdown"
    )

@dp.message(F.text == "🎫 Промокод")
async def promo_prompt(message: types.Message, state: FSMContext):
    await state.set_state(UserStates.waiting_for_promo_code)
    await message.answer("✏️ Введите промокод:", parse_mode="Markdown")

@dp.message(UserStates.waiting_for_promo_code)
async def promo_activate(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    promo = get_promocode(code)
    if not promo:
        await message.answer("❌ Неверный промокод.")
        await state.clear()
        return
    code_db, days, used_by, used_at = promo
    if used_by:
        await message.answer("❌ Промокод уже использован.")
        await state.clear()
        return
    tg_id = message.from_user.id
    use_promocode(code, tg_id)
    # Выдаём подписку на days дней (используем пул, подходящий по дням)
    pool = get_pool_for_days(days)
    link_data = get_free_link_from_pool(pool)
    if not link_data:
        await message.answer("❌ Нет свободных ссылок для активации промокода. Обратитесь к администратору.")
        await state.clear()
        return
    link_id, link = link_data
    mark_link_used_in_pool(pool, link_id, tg_id)
    expire_ts = int(time.time()) + days * 86400
    add_or_update_user(tg_id, f"promo_{code}", expire_ts, current_link=link)
    await message.answer(
        f"✅ Промокод активирован! Подписка на {days} дней.\n"
        f"🔗 Ваша ссылка:\n`{link}`\n\n"
        "📌 Вставьте её в V2RayTun / Happ.",
        parse_mode="Markdown"
    )
    await state.clear()

@dp.message(F.text == "📢 Канал")
async def channel_info(message: types.Message):
    await message.answer(f"📢 Наш канал: {CHANNEL_ID}\nПодпишитесь, чтобы быть в курсе новостей и получать бонусы!")

@dp.message(F.text == "❓ Поддержка")
async def support(message: types.Message):
    await message.answer(f"❓ По всем вопросам обращайтесь: @{PAYMENT_CONTACT}")

@dp.message(F.text == "📜 Соглашение")
async def agreement(message: types.Message):
    await message.answer(
        "📜 *Пользовательское соглашение*\n\n"
        "Используя нашего бота, вы соглашаетесь с условиями:\n"
        "1. Доступ предоставляется на указанный срок.\n"
        "2. Запрещено использовать VPN для незаконных действий.\n"
        "3. Мы не несём ответственности за ваши действия в сети.\n"
        "4. Администрация оставляет за собой право блокировать доступ при нарушении правил.",
        parse_mode="Markdown"
    )

@dp.message(F.text == "ℹ️ Политика")
async def policy(message: types.Message):
    await message.answer(
        "ℹ️ *Политика конфиденциальности*\n\n"
        "Мы не собираем и не храним ваши личные данные, кроме Telegram ID для работы бота. "
        "Ваши данные не передаются третьим лицам.",
        parse_mode="Markdown"
    )

# ------------------------- ЗАПУСК -------------------------
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
