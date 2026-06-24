"""
💈 Barbershop Bot «Sharp»
🇷🇺 Русский + 🇺🇦 Украинский | SQLite | Календарь | Админ-уведомления
Стек: Python 3.10+ | aiogram 3.x
"""

import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ══════════════════════════════════════════════════════════════════════════════
#  ⚙️  НАСТРОЙКИ — меняй только здесь
# ══════════════════════════════════════════════════════════════════════════════

BOT_TOKEN  = os.getenv("BOT_TOKEN")
ADMIN_ID   = int(os.getenv("ADMIN_ID", "0"))

# Слоты времени (можно добавить/убрать)
TIME_SLOTS = ["10:00","11:00","12:00","13:00","14:00","15:00","16:00","17:00","18:00"]

# Сколько дней вперёд показывать в календаре
CALENDAR_DAYS = 14

# ══════════════════════════════════════════════════════════════════════════════
#  🗄️  БАЗА ДАННЫХ
# ══════════════════════════════════════════════════════════════════════════════

DB_FILE = "bookings.db"

def db_init():
    with sqlite3.connect(DB_FILE) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  INTEGER NOT NULL,
                username TEXT,
                master   TEXT NOT NULL,
                date     TEXT NOT NULL,
                time     TEXT NOT NULL,
                service  TEXT NOT NULL,
                created  TEXT NOT NULL
            )
        """)
        # Миграция: добавляем username если старая БД без этой колонки
        cols = {row[1] for row in con.execute("PRAGMA table_info(bookings)")}
        if "username" not in cols:
            con.execute("ALTER TABLE bookings ADD COLUMN username TEXT DEFAULT ''")

def db_taken_times(master: str, date: str) -> set:
    """Занятые слоты мастера на дату"""
    with sqlite3.connect(DB_FILE) as con:
        rows = con.execute(
            "SELECT time FROM bookings WHERE master=? AND date=?", (master, date)
        ).fetchall()
    return {r[0] for r in rows}

def db_is_taken(master: str, date: str, time: str) -> bool:
    with sqlite3.connect(DB_FILE) as con:
        row = con.execute(
            "SELECT id FROM bookings WHERE master=? AND date=? AND time=?",
            (master, date, time)
        ).fetchone()
    return row is not None

def db_save(user_id: int, username: str, master: str,
            date: str, time: str, service: str):
    with sqlite3.connect(DB_FILE) as con:
        con.execute(
            "INSERT INTO bookings (user_id,username,master,date,time,service,created) "
            "VALUES (?,?,?,?,?,?,?)",
            (user_id, username, master, date, time, service,
             datetime.now().strftime("%Y-%m-%d %H:%M"))
        )

# ══════════════════════════════════════════════════════════════════════════════
#  📅  КАЛЕНДАРЬ
# ══════════════════════════════════════════════════════════════════════════════

WEEKDAYS_RU = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]
WEEKDAYS_UK = ["Пн","Вт","Ср","Чт","Пт","Сб","Нд"]
MONTHS_RU   = ["янв","фев","мар","апр","май","июн","июл","авг","сен","окт","ноя","дек"]
MONTHS_UK   = ["січ","лют","бер","кві","тра","чер","лип","сер","вер","жов","лис","гру"]

def get_calendar_dates() -> list[datetime]:
    """14 дней начиная с сегодня"""
    today = datetime.now().date()
    return [datetime.combine(today + timedelta(days=i), datetime.min.time())
            for i in range(CALENDAR_DAYS)]

def format_date_label(dt: datetime, lang: str) -> str:
    """Красивая метка для кнопки: 'Сб 21 июн'"""
    wd = WEEKDAYS_RU[dt.weekday()] if lang == "ru" else WEEKDAYS_UK[dt.weekday()]
    mo = MONTHS_RU[dt.month - 1]   if lang == "ru" else MONTHS_UK[dt.month - 1]
    return f"{wd} {dt.day} {mo}"

def format_date_key(dt: datetime) -> str:
    """Ключ для БД: '2025-06-21'"""
    return dt.strftime("%Y-%m-%d")

def calendar_kb(lang: str) -> object:
    """Инлайн-клавиатура с датами 3 в ряд"""
    dates = get_calendar_dates()
    kb = InlineKeyboardBuilder()
    for dt in dates:
        label = format_date_label(dt, lang)
        key   = format_date_key(dt)
        kb.button(text=label, callback_data=f"dat:{key}")
    kb.button(text=T[lang]["btn_back"], callback_data="book_start")
    kb.adjust(3)
    return kb.as_markup()

def time_kb(lang: str, master: str, date: str) -> object:
    """Слоты времени — занятые помечены 🔴"""
    taken = db_taken_times(master, date)
    kb = InlineKeyboardBuilder()
    for slot in TIME_SLOTS:
        if slot in taken:
            kb.button(text=f"🔴 {slot}", callback_data=f"tim_taken:{slot}")
        else:
            kb.button(text=slot, callback_data=f"tim:{slot}")
    kb.button(text=T[lang]["btn_back"], callback_data="book_date")
    kb.adjust(3)
    return kb.as_markup()

# ══════════════════════════════════════════════════════════════════════════════
#  🌐  ТЕКСТЫ
# ══════════════════════════════════════════════════════════════════════════════

T = {
    "ru": {
        # Общее
        "welcome": (
            "✂️ <b>Barbershop «Sharp»</b>\n\n"
            "Привет! Я помогу записаться на стрижку, "
            "узнать цены и найти нас на карте.\n\n"
            "Выбери язык / Оберіть мову:"
        ),
        "main_menu": "✂️ <b>Главное меню</b>\nЧто тебя интересует?",
        "btn_book":     "📅 Записаться",
        "btn_services": "💰 Услуги и цены",
        "btn_masters":  "👨‍🎨 Наши мастера",
        "btn_contacts": "📍 Адрес и контакты",
        "btn_back":     "⬅️ Назад",
        "btn_main":     "🏠 Главное меню",
        # Инфо-страницы
        "services": (
            "💰 <b>Услуги и цены</b>\n\n"
            "✂️ Мужская стрижка — <b>300 грн</b>\n"
            "🪒 Стрижка + борода — <b>450 грн</b>\n"
            "👶 Детская стрижка — <b>200 грн</b>\n"
            "🪒 Оформление бороды — <b>200 грн</b>\n"
            "💆 Голливудское бритьё — <b>350 грн</b>\n"
            "🎨 Камуфляж седины — <b>400 грн</b>\n\n"
            "⏱ Запись по времени, без очередей!"
        ),
        "masters": (
            "👨‍🎨 <b>Наши мастера</b>\n\n"
            "💈 <b>Артём</b> — топ-барбер, 7 лет\n"
            "Классика, фейд, борода\n\n"
            "💈 <b>Максим</b> — стрижки и укладки\n"
            "Современные стили, текстура\n\n"
            "💈 <b>Дмитрий</b> — мастер по бороде\n"
            "Борода, бритьё, моделирование"
        ),
        "contacts": (
            "📍 <b>Как нас найти</b>\n\n"
            "🗺 Одесса, ул. Дерибасовская, 5\n"
            "📞 +38 (063) 123-45-67\n"
            "📸 @sharp_barber_odessa\n\n"
            "🕐 Пн–Пт: 10:00–20:00\n"
            "🕐 Сб–Вс: 10:00–18:00"
        ),
        # FSM
        "step_service": "📋 <b>Шаг 1/4</b> — Выбери услугу:",
        "step_master":  "👨‍🎨 <b>Шаг 2/4</b> — Выбери мастера:",
        "step_date":    "📅 <b>Шаг 3/4</b> — Выбери день:",
        "step_time":    "🕐 <b>Шаг 4/4</b> — Выбери время:\n<i>🔴 — занято</i>",
        "confirm_text": (
            "✅ <b>Подтверди запись</b>\n\n"
            "📋 {service}\n"
            "👨‍🎨 {master}\n"
            "📅 {date}\n"
            "🕐 {time}\n\nВсё верно?"
        ),
        "done_text": (
            "🎉 <b>Запись подтверждена!</b>\n\n"
            "📋 {service}\n"
            "👨‍🎨 Мастер: {master}\n"
            "📅 {date} в {time}\n\n"
            "Мы свяжемся с тобой за час до визита.\n"
            "До встречи в Sharp! ✂️"
        ),
        "slot_taken":   "⚠️ Время только что заняли! Выбери другое:",
        "cancelled":    "❌ Запись отменена.",
        "btn_yes":      "✅ Подтвердить",
        "btn_no":       "❌ Отменить",
        # Данные для кнопок
        "services_list": [
            "✂️ Мужская стрижка — 300 грн",
            "🪒 Стрижка + борода — 450 грн",
            "👶 Детская стрижка — 200 грн",
            "🪒 Оформление бороды — 200 грн",
            "💆 Голливудское бритьё — 350 грн",
        ],
        "masters_list": ["💈 Артём", "💈 Максим", "💈 Дмитрий"],
        # Уведомление админу
        "admin_notify": (
            "🔔 <b>Новая запись!</b>\n\n"
            "👤 Клиент: {name} (@{username})\n"
            "📋 Услуга: {service}\n"
            "👨‍🎨 Мастер: {master}\n"
            "📅 {date} в {time}"
        ),
    },
    "uk": {
        "welcome": (
            "✂️ <b>Barbershop «Sharp»</b>\n\n"
            "Привіт! Я допоможу записатись на стрижку, "
            "дізнатись ціни та знайти нас на карті.\n\n"
            "Виберіть мову / Выбери язык:"
        ),
        "main_menu": "✂️ <b>Головне меню</b>\nЩо тебе цікавить?",
        "btn_book":     "📅 Записатись",
        "btn_services": "💰 Послуги та ціни",
        "btn_masters":  "👨‍🎨 Наші майстри",
        "btn_contacts": "📍 Адреса та контакти",
        "btn_back":     "⬅️ Назад",
        "btn_main":     "🏠 Головне меню",
        "services": (
            "💰 <b>Послуги та ціни</b>\n\n"
            "✂️ Чоловіча стрижка — <b>300 грн</b>\n"
            "🪒 Стрижка + борода — <b>450 грн</b>\n"
            "👶 Дитяча стрижка — <b>200 грн</b>\n"
            "🪒 Оформлення бороди — <b>200 грн</b>\n"
            "💆 Голлівудське гоління — <b>350 грн</b>\n"
            "🎨 Камуфляж сивини — <b>400 грн</b>\n\n"
            "⏱ Запис за часом, без черг!"
        ),
        "masters": (
            "👨‍🎨 <b>Наші майстри</b>\n\n"
            "💈 <b>Артем</b> — топ-барбер, 7 років\n"
            "Класика, фейд, борода\n\n"
            "💈 <b>Максим</b> — стрижки та укладки\n"
            "Сучасні стилі, текстура\n\n"
            "💈 <b>Дмитро</b> — майстер по бороді\n"
            "Борода, гоління, моделювання"
        ),
        "contacts": (
            "📍 <b>Як нас знайти</b>\n\n"
            "🗺 Одеса, вул. Дерибасівська, 5\n"
            "📞 +38 (063) 123-45-67\n"
            "📸 @sharp_barber_odessa\n\n"
            "🕐 Пн–Пт: 10:00–20:00\n"
            "🕐 Сб–Нд: 10:00–18:00"
        ),
        "step_service": "📋 <b>Крок 1/4</b> — Обери послугу:",
        "step_master":  "👨‍🎨 <b>Крок 2/4</b> — Обери майстра:",
        "step_date":    "📅 <b>Крок 3/4</b> — Обери день:",
        "step_time":    "🕐 <b>Крок 4/4</b> — Обери час:\n<i>🔴 — зайнято</i>",
        "confirm_text": (
            "✅ <b>Підтверди запис</b>\n\n"
            "📋 {service}\n"
            "👨‍🎨 {master}\n"
            "📅 {date}\n"
            "🕐 {time}\n\nВсе вірно?"
        ),
        "done_text": (
            "🎉 <b>Запис підтверджено!</b>\n\n"
            "📋 {service}\n"
            "👨‍🎨 Майстер: {master}\n"
            "📅 {date} о {time}\n\n"
            "Ми зателефонуємо за годину до візиту.\n"
            "До зустрічі у Sharp! ✂️"
        ),
        "slot_taken":   "⚠️ Час щойно зайняли! Обери інший:",
        "cancelled":    "❌ Запис скасовано.",
        "btn_yes":      "✅ Підтвердити",
        "btn_no":       "❌ Скасувати",
        "services_list": [
            "✂️ Чоловіча стрижка — 300 грн",
            "🪒 Стрижка + борода — 450 грн",
            "👶 Дитяча стрижка — 200 грн",
            "🪒 Оформлення бороди — 200 грн",
            "💆 Голлівудське гоління — 350 грн",
        ],
        "masters_list": ["💈 Артем", "💈 Максим", "💈 Дмитро"],
        "admin_notify": (
            "🔔 <b>Новий запис!</b>\n\n"
            "👤 Клієнт: {name} (@{username})\n"
            "📋 Послуга: {service}\n"
            "👨‍🎨 Майстер: {master}\n"
            "📅 {date} о {time}"
        ),
    }
}

# ══════════════════════════════════════════════════════════════════════════════
#  🤖  AIOGRAM SETUP
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

class Booking(StatesGroup):
    service = State()
    master  = State()
    date    = State()
    time    = State()
    confirm = State()

# ─── Helpers ──────────────────────────────────────────────────────────────────

def lang(data: dict) -> str:
    return data.get("lang", "ru")

def main_menu_kb(lg: str):
    kb = InlineKeyboardBuilder()
    kb.button(text=T[lg]["btn_book"],     callback_data="book_start")
    kb.button(text=T[lg]["btn_services"], callback_data="info_services")
    kb.button(text=T[lg]["btn_masters"],  callback_data="info_masters")
    kb.button(text=T[lg]["btn_contacts"], callback_data="info_contacts")
    kb.adjust(1)
    return kb.as_markup()

def back_main_kb(lg: str):
    kb = InlineKeyboardBuilder()
    kb.button(text=T[lg]["btn_main"], callback_data="main_menu")
    return kb.as_markup()

def list_kb(items: list, prefix: str, lg: str, back: str):
    kb = InlineKeyboardBuilder()
    for i, item in enumerate(items):
        kb.button(text=item, callback_data=f"{prefix}:{i}")
    kb.button(text=T[lg]["btn_back"], callback_data=back)
    kb.adjust(1)
    return kb.as_markup()

def confirm_kb(lg: str):
    kb = InlineKeyboardBuilder()
    kb.button(text=T[lg]["btn_yes"], callback_data="confirm_yes")
    kb.button(text=T[lg]["btn_no"],  callback_data="confirm_no")
    kb.adjust(2)
    return kb.as_markup()

async def notify_admin(lg: str, data: dict, user):
    """Отправить уведомление администратору"""
    try:
        username = user.username or "—"
        name     = user.full_name or "—"
        text = T[lg]["admin_notify"].format(
            name=name, username=username,
            service=data["service"], master=data["master"],
            date=data["date"], time=data["time"]
        )
        await bot.send_message(ADMIN_ID, text, parse_mode="HTML")
    except Exception as e:
        logging.warning(f"Не удалось отправить уведомление админу: {e}")

# ══════════════════════════════════════════════════════════════════════════════
#  🔧  ХЕНДЛЕРЫ
# ══════════════════════════════════════════════════════════════════════════════

@dp.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(T["ru"]["welcome"], reply_markup=_lang_kb(), parse_mode="HTML")

def _lang_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🇷🇺 Русский",     callback_data="lang:ru")
    kb.button(text="🇺🇦 Українська", callback_data="lang:uk")
    kb.adjust(2)
    return kb.as_markup()

@dp.callback_query(F.data.startswith("lang:"))
async def set_lang(call: CallbackQuery, state: FSMContext):
    lg = call.data.split(":")[1]
    await state.update_data(lang=lg)
    await call.message.edit_text(T[lg]["main_menu"], reply_markup=main_menu_kb(lg), parse_mode="HTML")

@dp.callback_query(F.data == "main_menu")
async def go_main(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lg = lang(data)
    await state.clear()
    await state.update_data(lang=lg)
    await call.message.edit_text(T[lg]["main_menu"], reply_markup=main_menu_kb(lg), parse_mode="HTML")

# ─── Инфо-страницы ────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "info_services")
async def info_services(call: CallbackQuery, state: FSMContext):
    lg = lang(await state.get_data())
    await call.message.edit_text(T[lg]["services"], reply_markup=back_main_kb(lg), parse_mode="HTML")

@dp.callback_query(F.data == "info_masters")
async def info_masters(call: CallbackQuery, state: FSMContext):
    lg = lang(await state.get_data())
    await call.message.edit_text(T[lg]["masters"], reply_markup=back_main_kb(lg), parse_mode="HTML")

@dp.callback_query(F.data == "info_contacts")
async def info_contacts(call: CallbackQuery, state: FSMContext):
    lg = lang(await state.get_data())
    await call.message.edit_text(T[lg]["contacts"], reply_markup=back_main_kb(lg), parse_mode="HTML")

# ─── FSM: запись ──────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "book_start")
async def step_service(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lg = lang(data)
    await state.set_state(Booking.service)
    await call.message.edit_text(
        T[lg]["step_service"],
        reply_markup=list_kb(T[lg]["services_list"], "svc", lg, "main_menu"),
        parse_mode="HTML"
    )

@dp.callback_query(Booking.service, F.data.startswith("svc:"))
async def step_master(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lg = lang(data)
    idx = int(call.data.split(":")[1])
    await state.update_data(service=T[lg]["services_list"][idx])
    await state.set_state(Booking.master)
    await call.message.edit_text(
        T[lg]["step_master"],
        reply_markup=list_kb(T[lg]["masters_list"], "mst", lg, "book_start"),
        parse_mode="HTML"
    )

@dp.callback_query(Booking.master, F.data.startswith("mst:"))
async def step_date(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lg = lang(data)
    idx = int(call.data.split(":")[1])
    await state.update_data(master=T[lg]["masters_list"][idx])
    await state.set_state(Booking.date)
    await call.message.edit_text(
        T[lg]["step_date"],
        reply_markup=calendar_kb(lg),
        parse_mode="HTML"
    )

@dp.callback_query(Booking.date, F.data.startswith("dat:"))
async def step_time(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lg = lang(data)
    date_key = call.data.split(":")[1]          # "2025-06-21"
    # Красивая дата для отображения
    dt = datetime.strptime(date_key, "%Y-%m-%d")
    date_label = format_date_label(dt, lg)
    await state.update_data(date=date_label, date_key=date_key)
    await state.set_state(Booking.time)
    await call.message.edit_text(
        T[lg]["step_time"],
        reply_markup=time_kb(lg, data.get("master", ""), date_key),
        parse_mode="HTML"
    )

# Кнопка «назад» со шага времени — возврат к календарю
@dp.callback_query(Booking.time, F.data == "book_date")
async def back_to_date(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lg = lang(data)
    await state.set_state(Booking.date)
    await call.message.edit_text(
        T[lg]["step_date"],
        reply_markup=calendar_kb(lg),
        parse_mode="HTML"
    )

@dp.callback_query(Booking.time, F.data.startswith("tim_taken:"))
async def slot_taken(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lg = lang(data)
    await call.answer("⚠️ Это время уже занято!", show_alert=True)
    await call.message.edit_text(
        T[lg]["slot_taken"],
        reply_markup=time_kb(lg, data.get("master", ""), data.get("date_key", "")),
        parse_mode="HTML"
    )

@dp.callback_query(Booking.time, F.data.startswith("tim:"))
async def step_confirm(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lg = lang(data)
    time_val = call.data.split(":")[1]
    master   = data.get("master", "")
    date_key = data.get("date_key", "")

    # Двойная проверка — вдруг слот заняли пока выбирал
    if db_is_taken(master, date_key, time_val):
        await call.answer("⚠️ Только что заняли! Выбери другое.", show_alert=True)
        await call.message.edit_text(
            T[lg]["slot_taken"],
            reply_markup=time_kb(lg, master, date_key),
            parse_mode="HTML"
        )
        return

    await state.update_data(time=time_val)
    await state.set_state(Booking.confirm)
    d = await state.get_data()
    await call.message.edit_text(
        T[lg]["confirm_text"].format(
            service=d["service"], master=d["master"],
            date=d["date"], time=d["time"]
        ),
        reply_markup=confirm_kb(lg),
        parse_mode="HTML"
    )

@dp.callback_query(Booking.confirm, F.data == "confirm_yes")
async def booking_done(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lg   = lang(data)

    # Финальная проверка перед сохранением
    if db_is_taken(data["master"], data["date_key"], data["time"]):
        await call.answer("⚠️ Время только что заняли!", show_alert=True)
        await state.set_state(Booking.time)
        await call.message.edit_text(
            T[lg]["slot_taken"],
            reply_markup=time_kb(lg, data["master"], data["date_key"]),
            parse_mode="HTML"
        )
        return

    # Сохраняем запись
    db_save(
        user_id=call.from_user.id,
        username=call.from_user.username or "",
        master=data["master"], date=data["date_key"],
        time=data["time"],     service=data["service"]
    )

    # Уведомляем админа
    await notify_admin(lg, data, call.from_user)

    await state.clear()
    await state.update_data(lang=lg)
    await call.message.edit_text(
        T[lg]["done_text"].format(
            service=data["service"], master=data["master"],
            date=data["date"], time=data["time"]
        ),
        reply_markup=back_main_kb(lg),
        parse_mode="HTML"
    )

@dp.callback_query(Booking.confirm, F.data == "confirm_no")
async def booking_cancel(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lg   = lang(data)
    await state.clear()
    await state.update_data(lang=lg)
    await call.message.edit_text(
        T[lg]["cancelled"],
        reply_markup=back_main_kb(lg),
        parse_mode="HTML"
    )

# ══════════════════════════════════════════════════════════════════════════════
#  🚀  ЗАПУСК
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    db_init()
    logging.info("🚀 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())