import asyncio
import time
import os
import logging
import random
import string
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    FSInputFile, LabeledPrice, PreCheckoutQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from config import (
    BOT_TOKEN, ADMIN_IDS, VPN_NAME, DB_PATH,
    CHANNEL_ID, PAYMENT_CONTACT, IMAGE_PATH, BOT_USERNAME, TARIFFS
)
from database import (
    init_db, get_user, add_or_update_user, delete_user, get_all_active_users,
    add_promocode, get_promocode, use_promocode, get_all_promocodes,
    get_setting, set_setting
)
from panel_api import create_client, delete_client, extend_client
from utils import format_time_left, format_datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_tariff = State()
    waiting_for_ref_user_id = State()
    waiting_for_promo_days = State()
    waiting_for_broadcast_text = State()
    waiting_for_broadcast_confirm = State()
    waiting_for_ref_settings = State()
    waiting_for_client_action = State()


class UserStates(StatesGroup):
    waiting_for_promo_code = State()


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
        [KeyboardButton(text="🎁 Активировать реферальную")],
        [KeyboardButton(text="🗑️ Удалить клиента")],
        [KeyboardButton(text="📅 Продлить клиента")],
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
    [InlineKeyboardButton(text="📢 Подписаться на канал", url="https://t.me/%s" % CHANNEL_ID.lstrip("@"))],
    [InlineKeyboardButton(text="🔄 Проверить подписку", callback_data="check_sub")]
])


def build_sub_message(title, tariff_label, days, expire_ts, sub_link, relay_link):
    """Формирует красивое сообщение с подпиской и relay-ссылкой."""
    return (
        "✅ *%s*\n\n"
        "▸ Тариф: *%s*\n"
        "▸ Срок: *%d дней*\n"
        "▸ Действует до: *%s*\n\n"
        "🔗 *Ссылка подписки* (Wi-Fi + резерв, 2 сервера):\n"
        "`%s`\n\n"
        "📱 *Ссылка для мобильного* (relay, обход белых списков):\n"
        "`%s`\n\n"
        "📌 Для Wi-Fi используйте первую ссылку в V2RayTun/Happ.\n"
        "Для мобильного интернета — вторую (relay) отдельным подключением."
    ) % (title, tariff_label, days, format_datetime(expire_ts), sub_link, relay_link)


async def check_subscription(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False


@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    args = message.text.split()
    if len(args) > 1:
        ref_data = args[1]
        if ref_data.startswith("ref_"):
            rid = ref_data[4:]
            if rid.isdigit():
                referrer_id = int(rid)
                if referrer_id != message.from_user.id:
                    await handle_referral(message.from_user.id, referrer_id)

    welcome_text = (
        "✨ Добро пожаловать в " + VPN_NAME + "!\n\n"
        "Быстрый, стабильный и приватный VPN в пару кликов 🚀\n\n"
        "✅ Бесплатная подписка — «Получить подписку»\n"
        "💰 Купить — через «Прайс и оплата»\n"
        "🎁 Пробный период — кнопка «Пробный период»\n"
        "📖 Инструкция — в разделе «Инструкция» 🎯"
    )

    if os.path.exists(IMAGE_PATH):
        try:
            await message.answer_photo(photo=FSInputFile(IMAGE_PATH), caption=welcome_text, reply_markup=main_menu)
        except Exception as e:
            logger.error("photo error: %s" % e)
            await message.answer(welcome_text, reply_markup=main_menu)
    else:
        await message.answer(welcome_text, reply_markup=main_menu)

    await message.answer("👇 Нижнее меню:", reply_markup=bottom_menu)


@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Нет прав.")
        return
    await message.answer("👋 Админ-панель " + VPN_NAME, reply_markup=admin_keyboard)


async def handle_referral(new_user_id, referrer_id):
    if get_user(new_user_id):
        return
    add_or_update_user(new_user_id, None, 0, referrer_id=referrer_id)
    referrer = get_user(referrer_id)
    if not referrer:
        return
    new_count = referrer[4] + 1
    add_or_update_user(referrer_id, referrer[0], referrer[1],
                       last_free=referrer[3], used_free=referrer[4],
                       ref_count=new_count, referrer_id=referrer[5],
                       current_link=referrer[6], ref_link=referrer[7])
    required = int(get_setting("ref_required") or 5)
    if new_count >= required:
        await give_ref_bonus(referrer_id)


async def give_ref_bonus(tg_id):
    bonus_days = int(get_setting("ref_bonus_days") or 14)
    try:
        cd = create_client(bonus_days, email="ref_%d_%d" % (tg_id, int(time.time())))
        add_or_update_user(tg_id, "ref_bonus", cd["expiry_time"],
                           current_link=cd["link"], panel_client_id=cd["id"], uuid=cd["uuid"])
        await bot.send_message(
            tg_id,
            build_sub_message("🎉 Реферальный бонус!", "Реферальная", bonus_days,
                              cd["expiry_time"], cd["link"], cd.get("relay_link", "")),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error("ref bonus error: %s" % e)


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
        ref_link = "ref_%d" % tg_id
        add_or_update_user(tg_id, user[0], user[1],
                           last_free=user[3] if user else 0,
                           used_free=user[4] if user else 0,
                           ref_count=ref_count,
                           referrer_id=user[5] if user else None,
                           current_link=user[6] if user else None,
                           ref_link=ref_link)
    ref_url = "https://t.me/%s?start=%s" % (BOT_USERNAME, ref_link)
    await message.answer(
        "👥 Реферальная программа\n\nПриводите друзей!\nЗа каждых %d друзей +%d дней.\n\n📊 Ваши рефералы: %d/%d\n🔗 Ваша ссылка:\n%s" %
        (required, bonus_days, ref_count, required, ref_url))


@dp.callback_query(F.data == "get_free")
async def get_free(callback: types.CallbackQuery):
    tg_id = callback.from_user.id
    user = get_user(tg_id)
    now = int(time.time())

    if user and user[1] and user[1] > now:
        await callback.answer("У вас уже есть активная подписка.", show_alert=True)
        return
    if user and user[3] == 1:
        if user[6] and user[1] and user[1] > now:
            await callback.message.answer("🔁 У вас уже есть активная подписка:\n" + user[6], reply_markup=back_button)
            return
        await callback.answer("❌ Бесплатную подписку уже использовали.", show_alert=True)
        return

    if not await check_subscription(tg_id):
        await callback.message.answer("🔒 Подпишитесь на канал для получения подписки.", reply_markup=subscribe_keyboard)
        return

    try:
        cd = create_client(1, email="free_%d_%d" % (tg_id, int(time.time())))
        add_or_update_user(tg_id, "free", cd["expiry_time"], used_free=1,
                           current_link=cd["link"], panel_client_id=cd["id"], uuid=cd["uuid"])
        await callback.message.answer(
            build_sub_message("Бесплатная подписка активирована! 🎉", "Бесплатная", 1,
                              cd["expiry_time"], cd["link"], cd.get("relay_link", "")),
            parse_mode="Markdown",
            reply_markup=back_button)
    except Exception as e:
        logger.error("get_free error: %s" % e)
        await callback.message.answer("❌ Ошибка при создании подписки. Админ уведомлён.")
        for a in ADMIN_IDS:
            try:
                await bot.send_message(a, "Ошибка выдачи free: %s" % e)
            except:
                pass


@dp.callback_query(F.data == "buy_menu")
async def buy_menu(callback: types.CallbackQuery):
    text = "💎 Наши тарифы:\n\n"
    for k, t in TARIFFS.items():
        if k in ("free", "ref"):
            continue
        text += "▸ %s — %d дн.\n   ⭐ %d звёзд / 💳 %s руб.\n\n" % (t["label"], t["days"], t["price_stars"], t["price_rub"])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Оплатить звёздами", callback_data="buy_stars_menu")],
        [InlineKeyboardButton(text="💳 Оплатить рублями", callback_data="buy_manual")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ])
    if callback.message.text:
        await callback.message.edit_text(text, reply_markup=kb)
    else:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "buy_stars_menu")
async def buy_stars_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for k, t in TARIFFS.items():
        if k in ("free", "ref"):
            continue
        kb.inline_keyboard.append([InlineKeyboardButton(
            text="%s — %d ⭐" % (t["label"], t["price_stars"]),
            callback_data="stars_%s" % k
        )])
    kb.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="buy_menu")])
    if callback.message.text:
        await callback.message.edit_text("⭐ Выберите тариф:", reply_markup=kb)
    else:
        await callback.message.answer("⭐ Выберите тариф:", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "buy_manual")
async def buy_manual(callback: types.CallbackQuery):
    text = "💳 Оплата рублями через администратора\n\n"
    for k, t in TARIFFS.items():
        if k in ("free", "ref"):
            continue
        text += "▸ %s — %d дн. | %s руб.\n" % (t["label"], t["days"], t["price_rub"])
    text += "\n📩 Свяжитесь: @" + PAYMENT_CONTACT
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="buy_menu")]])
    if callback.message.text:
        await callback.message.edit_text(text, reply_markup=kb)
    else:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data.startswith("stars_"))
async def buy_stars(callback: types.CallbackQuery):
    key = callback.data.split("_", 1)[1]
    t = TARIFFS.get(key)
    if not t:
        await callback.answer("Тариф не найден", show_alert=True)
        return
    await callback.message.answer_invoice(
        title="Подписка %s — %s" % (VPN_NAME, t["label"]),
        description="Доступ на %d дней" % t["days"],
        payload="stars_%s_%d" % (key, callback.from_user.id),
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=t["label"], amount=t["price_stars"])],
        start_parameter="sub"
    )
    await callback.answer()


@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)


@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    p = message.successful_payment
    parts = p.invoice_payload.split("_")
    if len(parts) != 3 or parts[0] != "stars":
        return
    key = parts[1]
    tg_id = int(parts[2])
    t = TARIFFS.get(key)
    if not t:
        return
    try:
        cd = create_client(t["days"], email="paid_%d_%d" % (tg_id, int(time.time())))
        add_or_update_user(tg_id, "paid_%s" % key, cd["expiry_time"],
                           current_link=cd["link"], panel_client_id=cd["id"], uuid=cd["uuid"])
        await message.answer(
            build_sub_message("Оплата прошла успешно! 🎉", t["label"], t["days"],
                              cd["expiry_time"], cd["link"], cd.get("relay_link", "")),
            parse_mode="Markdown")
    except Exception as e:
        logger.error("payment error: %s" % e)
        await message.answer("❌ Ошибка активации. Админ уведомлён.")
        for a in ADMIN_IDS:
            try:
                await bot.send_message(a, "Ошибка оплаты: %s" % e)
            except:
                pass


@dp.message(F.text == "✅ Активировать подписку")
async def activate_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_user_id)
    await message.answer("✏️ Введите ID пользователя. /cancel — отмена")


@dp.message(AdminStates.waiting_for_user_id)
async def activate_user(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=admin_keyboard)
        return
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите число.")
        return
    await state.update_data(user_id=uid)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📅 Неделя (7д)")],
        [KeyboardButton(text="📅 Месяц (30д)")],
        [KeyboardButton(text="📅 Полгода (180д)")],
        [KeyboardButton(text="📅 Год (365д)")],
        [KeyboardButton(text="📅 Навсегда (3650д)")],
        [KeyboardButton(text="🔙 Отмена")]
    ], resize_keyboard=True)
    await state.set_state(AdminStates.waiting_for_tariff)
    await message.answer("Выберите тариф:", reply_markup=kb)


@dp.message(AdminStates.waiting_for_tariff)
async def activate_tariff(message: types.Message, state: FSMContext):
    if message.text in ("🔙 Отмена", "/cancel"):
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=admin_keyboard)
        return
    tmap = {
        "📅 Неделя (7д)": "week", "📅 Месяц (30д)": "month", "📅 Полгода (180д)": "halfyear",
        "📅 Год (365д)": "year", "📅 Навсегда (3650д)": "forever"
    }
    key = tmap.get(message.text)
    if not key:
        await message.answer("❌ Неверный тариф.")
        return
    t = TARIFFS[key]
    data = await state.get_data()
    uid = data.get("user_id")
    try:
        cd = create_client(t["days"], email="admin_%d_%d" % (uid, int(time.time())))
        add_or_update_user(uid, "admin_%s" % key, cd["expiry_time"],
                           current_link=cd["link"], panel_client_id=cd["id"], uuid=cd["uuid"])
        try:
            await bot.send_message(
                uid,
                build_sub_message("🎉 Админ активировал подписку!", t["label"], t["days"],
                                  cd["expiry_time"], cd["link"], cd.get("relay_link", "")),
                parse_mode="Markdown")
        except:
            pass
        await message.answer("✅ Активировано для %d на %d дней" % (uid, t["days"]), reply_markup=admin_keyboard)
    except Exception as e:
        await message.answer("❌ Ошибка: %s" % e, reply_markup=admin_keyboard)
    await state.clear()


@dp.message(F.text == "🎁 Активировать реферальную")
async def activate_ref(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_ref_user_id)
    await message.answer("✏️ Введите ID для реф-подписки (14 дней). /cancel")


@dp.message(AdminStates.waiting_for_ref_user_id)
async def activate_ref_process(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=admin_keyboard)
        return
    try:
        uid = int(message.text.strip())
        cd = create_client(14, email="admin_ref_%d_%d" % (uid, int(time.time())))
        add_or_update_user(uid, "admin_ref", cd["expiry_time"],
                           current_link=cd["link"], panel_client_id=cd["id"], uuid=cd["uuid"])
        try:
            await bot.send_message(
                uid,
                build_sub_message("🎉 Реф-подписка от админа", "Реферальная", 14,
                                  cd["expiry_time"], cd["link"], cd.get("relay_link", "")),
                parse_mode="Markdown")
        except:
            pass
        await message.answer("✅ Реф-подписка для %d на 14 дней" % uid, reply_markup=admin_keyboard)
    except Exception as e:
        await message.answer("❌ Ошибка: %s" % e, reply_markup=admin_keyboard)
    await state.clear()


@dp.message(F.text == "🗑️ Удалить клиента")
async def del_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_client_action)
    await message.answer("✏️ Введите ID пользователя для удаления. /cancel")


@dp.message(AdminStates.waiting_for_client_action)
async def del_process(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=admin_keyboard)
        return
    try:
        uid = int(message.text.strip())
        u = get_user(uid)
        if not u or not u[8]:
            await message.answer("❌ Нет клиента.")
            await state.clear()
            return
        if delete_client(u[8]):
            delete_user(uid)
            await message.answer("✅ Удалён %d" % uid, reply_markup=admin_keyboard)
        else:
            await message.answer("❌ Не удалось удалить.", reply_markup=admin_keyboard)
    except Exception as e:
        await message.answer("❌ Ошибка: %s" % e, reply_markup=admin_keyboard)
    await state.clear()


@dp.message(F.text == "📅 Продлить клиента")
async def ext_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_client_action)
    await message.answer("✏️ Введите ID и дни через пробел. /cancel")


@dp.message(AdminStates.waiting_for_client_action)
async def ext_process(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=admin_keyboard)
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❌ Введите два числа.")
        return
    try:
        uid = int(parts[0])
        days = int(parts[1])
        u = get_user(uid)
        if not u or not u[8]:
            await message.answer("❌ Нет клиента.")
            await state.clear()
            return
        if extend_client(u[8], days):
            new_expire = (u[1] if u[1] > int(time.time()) else int(time.time())) + days * 86400
            add_or_update_user(uid, u[0], new_expire, current_link=u[6], panel_client_id=u[8], uuid=u[9])
            await message.answer("✅ Продлён %d на %d дней" % (uid, days), reply_markup=admin_keyboard)
        else:
            await message.answer("❌ Не удалось продлить.", reply_markup=admin_keyboard)
    except Exception as e:
        await message.answer("❌ Ошибка: %s" % e, reply_markup=admin_keyboard)
    await state.clear()


@dp.message(F.text == "⚙️ Реферальные настройки")
async def ref_settings(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_ref_settings)
    req = get_setting("ref_required") or 5
    bonus = get_setting("ref_bonus_days") or 14
    await message.answer("⚙️ Текущие: рефералов %s, дней %s\n\nВведите новые через пробел. /cancel" % (req, bonus))


@dp.message(AdminStates.waiting_for_ref_settings)
async def ref_settings_process(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=admin_keyboard)
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer("❌ Два числа через пробел.")
        return
    try:
        set_setting("ref_required", str(int(parts[0])))
        set_setting("ref_bonus_days", str(int(parts[1])))
        await state.clear()
        await message.answer("✅ Настройки обновлены", reply_markup=admin_keyboard)
    except ValueError:
        await message.answer("❌ Введите числа.")


@dp.message(F.text == "🎫 Создать промокод")
async def create_promo(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_promo_days)
    await message.answer("✏️ Введите количество дней. /cancel")


@dp.message(AdminStates.waiting_for_promo_days)
async def create_promo_process(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=admin_keyboard)
        return
    try:
        days = int(message.text.strip())
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=10))
        add_promocode(code, days)
        await state.clear()
        await message.answer("✅ Промокод: %s\nНа %d дней" % (code, days), reply_markup=admin_keyboard)
    except ValueError:
        await message.answer("❌ Число.")


@dp.message(F.text == "📋 Список промокодов")
async def list_promos(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    promos = get_all_promocodes()
    if not promos:
        await message.answer("📭 Нет промокодов.", reply_markup=admin_keyboard)
        return
    text = "📋 Промокоды:\n\n"
    for code, days, used_by, _, _ in promos:
        status = "❌" if used_by else "✅"
        text += "%s — %d дн. %s\n" % (code, days, status)
    await message.answer(text, reply_markup=admin_keyboard)


@dp.message(F.text == "📨 Сделать рассылку")
async def bc_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.waiting_for_broadcast_text)
    await message.answer("✏️ Введите текст рассылки. /cancel")


@dp.message(AdminStates.waiting_for_broadcast_text)
async def bc_process(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=admin_keyboard)
        return
    await state.update_data(bc_text=message.text)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="bc_yes")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="bc_no")]
    ])
    await state.set_state(AdminStates.waiting_for_broadcast_confirm)
    await message.answer("📨 Текст:\n\n%s\n\nПодтвердите:" % message.text, reply_markup=kb)


@dp.callback_query(F.data == "bc_yes", AdminStates.waiting_for_broadcast_confirm)
async def bc_yes(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get("bc_text")
    users = get_all_active_users()
    sent = 0
    for uid, _ in users:
        try:
            await bot.send_message(uid, text)
            sent += 1
            await asyncio.sleep(0.05)
        except:
            pass
    await callback.message.edit_text("✅ Отправлено %d" % sent)
    await state.clear()
    await callback.answer()


@dp.callback_query(F.data == "bc_no", AdminStates.waiting_for_broadcast_confirm)
async def bc_no(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Отменено")
    await state.clear()
    await callback.answer()


@dp.message(F.text == "📊 Статистика")
async def stats(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    users = get_all_active_users()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    conn.close()
    await message.answer("📊 Статистика:\n\n👥 Всего: %d\n✅ Активных: %d\n🎫 Промокодов: %d" %
                         (total, len(users), len(get_all_promocodes())),
                         reply_markup=admin_keyboard)


@dp.message(F.text == "👥 Список пользователей")
async def list_users(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT tg_id, tariff, expire_time FROM users ORDER BY tg_id")
    rows = c.fetchall()
    conn.close()
    if not rows:
        await message.answer("📭 Пусто.", reply_markup=admin_keyboard)
        return
    text = "👥 Пользователи:\n\n"
    for tg_id, tariff, exp in rows:
        st = "✅" if exp and exp > int(time.time()) else "❌"
        text += "%d | %s | %s\n" % (tg_id, tariff or "-", st)
    await message.answer(text, reply_markup=admin_keyboard)


@dp.callback_query(F.data == "back_main")
async def back_main(callback: types.CallbackQuery):
    if callback.message.text:
        try:
            await callback.message.edit_text("🏠 Главное меню:", reply_markup=main_menu)
        except:
            await callback.message.answer("🏠 Главное меню:", reply_markup=main_menu)
    else:
        await callback.message.answer("🏠 Главное меню:", reply_markup=main_menu)
    await callback.answer()


@dp.callback_query(F.data == "instructions")
async def instructions(callback: types.CallbackQuery):
    text = (
        "📖 Инструкция:\n\n"
        "1️⃣ Получите подписку через бота.\n"
        "2️⃣ Скопируйте ссылку подписки — она для Wi-Fi.\n"
        "3️⃣ Для мобильного интернета — используйте ОТДЕЛЬНУЮ relay-ссылку (вторую в сообщении).\n"
        "4️⃣ Вставьте в клиент (Happ / V2RayNG / Nekobox).\n"
        "5️⃣ Включите Allow Insecure.\n"
        "6️⃣ Подключайтесь 🚀"
    )
    if callback.message.text:
        try:
            await callback.message.edit_text(text, reply_markup=back_button)
        except:
            await callback.message.answer(text, reply_markup=back_button)
    else:
        await callback.message.answer(text, reply_markup=back_button)
    await callback.answer()


@dp.callback_query(F.data == "trial")
async def trial(callback: types.CallbackQuery):
    text = "🎁 Пробный период: нажмите «Получить подписку» для 24-часового доступа."
    if callback.message.text:
        try:
            await callback.message.edit_text(text, reply_markup=back_button)
        except:
            await callback.message.answer(text, reply_markup=back_button)
    else:
        await callback.message.answer(text, reply_markup=back_button)
    await callback.answer()


@dp.message(F.text == "🔙 Выйти из админ-панели")
async def exit_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("👋 Вышли", reply_markup=bottom_menu)


@dp.message(F.text == "👤 Профиль")
async def profile(message: types.Message):
    u = get_user(message.from_user.id)
    if not u:
        await message.answer("❌ Напишите /start")
        return
    status = "✅ активна" if u[1] and u[1] > int(time.time()) else "❌ неактивна"
    left = format_time_left(u[1]) if u[1] and u[1] > int(time.time()) else "-"
    await message.answer("👤 Профиль:\n\n▸ Тариф: %s\n▸ Статус: %s\n▸ До: %s\n▸ Осталось: %s\n▸ Рефералов: %s" %
                         (u[0] or "-", status,
                          format_datetime(u[1]) if u[1] else "-",
                          left, u[4]))


@dp.message(F.text == "🎫 Промокод")
async def promo_prompt(message: types.Message, state: FSMContext):
    await state.set_state(UserStates.waiting_for_promo_code)
    await message.answer("✏️ Введите промокод:")


@dp.message(UserStates.waiting_for_promo_code)
async def promo_activate(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    p = get_promocode(code)
    if not p or p[2]:
        await message.answer("❌ Неверный или использованный промокод.")
        await state.clear()
        return
    days = p[1]
    tg_id = message.from_user.id
    use_promocode(code, tg_id)
    try:
        cd = create_client(days, email="promo_%d_%d" % (tg_id, int(time.time())))
        add_or_update_user(tg_id, "promo_%s" % code, cd["expiry_time"],
                           current_link=cd["link"], panel_client_id=cd["id"], uuid=cd["uuid"])
        await message.answer(
            build_sub_message("✅ Промокод активирован!", "Промокод", days,
                              cd["expiry_time"], cd["link"], cd.get("relay_link", "")),
            parse_mode="Markdown")
    except Exception as e:
        logger.error("promo error: %s" % e)
        await message.answer("❌ Ошибка.")
    await state.clear()


@dp.message(F.text == "📢 Канал")
async def channel_info(message: types.Message):
    await message.answer("📢 Канал: " + CHANNEL_ID)


@dp.message(F.text == "❓ Поддержка")
async def support(message: types.Message):
    await message.answer("❓ Поддержка: @" + PAYMENT_CONTACT)


@dp.message(F.text == "📜 Соглашение")
async def agreement(message: types.Message):
    await message.answer("📜 Пользовательское соглашение. Используя сервис, вы соглашаетесь с правилами.")


@dp.message(F.text == "ℹ️ Политика")
async def policy(message: types.Message):
    await message.answer("ℹ️ Политика конфиденциальности. Мы не храним личные данные.")


@dp.callback_query(F.data == "check_sub")
async def check_sub(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.answer("✅ Подписка подтверждена. Нажмите «Получить подписку».")
    else:
        await callback.message.answer("❌ Вы ещё не подписались на канал.")
    await callback.answer()


async def main():
    init_db()
    logger.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
