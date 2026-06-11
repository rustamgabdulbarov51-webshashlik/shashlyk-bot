import logging
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ─── НАСТРОЙКИ ───────────────────────────────────────────────
WAITER_BOT_TOKEN = "8851091659:AAFDcVFsFH9hyhRcQivsHoeQmiRzzvomoX0"
COOK_BOT_TOKEN   = "8995232402:AAHIZwYJe9WU4S--pc0UDFCZacBPUlfJwjQ"
COOK_CHAT_ID     = 853166810  # Telegram ID шашлычника

# ─── МЕНЮ ────────────────────────────────────────────────────
MENU = {
    "🍗 Куриное бедро":     2900,
    "🍗 Курица филе":       3000,
    "🍗 Куриные крылья":    2800,
    "🐑 Баранина":          4000,
    "🐷 Свинина":           3600,
    "🦆 Утка":              3200,
    "🍄 Грибы":             2000,
    "🌭 Дачные сосиски":    1500,
    "🌭 Мексика":           1500,
    "🌭 Деревенские":       1500,
    "🌭 Гурман":            1500,
    "🌭 Куриные сосиски":   1500,
    "🥦 Овощи на гриле":    1800,
    "🐟 Линь с овощами":    3500,
    "🐟 Карась во фритюре": 2500,
}

MENU_KEYS = list(MENU.keys())

# ─── ХРАНИЛИЩЕ ЗАКАЗОВ ───────────────────────────────────────
orders = {}        # user_id -> {items: {name: qty}, table: str}
order_counter = 0  # глобальный счётчик заказов

# ─── ЛОГИРОВАНИЕ ─────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)

# ─── БОТЫ ────────────────────────────────────────────────────
waiter_bot = Bot(token=WAITER_BOT_TOKEN)
cook_bot   = Bot(token=COOK_BOT_TOKEN)

waiter_dp = Dispatcher(storage=MemoryStorage())

class OrderState(StatesGroup):
    choosing = State()
    table    = State()

# ─── КЛАВИАТУРЫ ──────────────────────────────────────────────
def menu_keyboard(cart: dict) -> InlineKeyboardMarkup:
    buttons = []
    for name in MENU_KEYS:
        qty = cart.get(name, 0)
        label = f"{name} — {MENU[name]}₸"
        if qty > 0:
            label = f"✅ {name} x{qty} — {MENU[name] * qty}₸"
        key = name.replace(" ", "_").replace("(", "").replace(")", "")
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"add_{key}")])

    # Итого и кнопки управления
    total = sum(MENU[n] * q for n, q in cart.items())
    if total > 0:
        buttons.append([
            InlineKeyboardButton(text=f"🛒 Итого: {total}₸  →  Оформить", callback_data="checkout")
        ])
        buttons.append([
            InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="clear")
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def confirm_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Принял в работу", callback_data=f"accept_{order_id}"),
        InlineKeyboardButton(text="❌ Отклонить",       callback_data=f"decline_{order_id}"),
    ]])

def ready_keyboard(order_id: int) -> InlineKeyboardMarkup:
    times = [10, 15, 20, 30, 45]
    row = [InlineKeyboardButton(text=f"⏱ {t} мин", callback_data=f"ready_{order_id}_{t}") for t in times]
    return InlineKeyboardMarkup(inline_keyboard=[row])

# ─── ВСПОМОГАТЕЛЬНЫЕ ─────────────────────────────────────────
def format_order(cart: dict, table: str, order_id: int, time_str: str) -> str:
    lines = [f"🔥 *ЗАКАЗ #{order_id}* — стол *{table}*", f"🕐 {time_str}", "─────────────────"]
    total = 0
    for name, qty in cart.items():
        price = MENU[name] * qty
        total += price
        lines.append(f"• {name} × {qty} — {price}₸")
    lines += ["─────────────────", f"💰 *Итого: {total}₸*"]
    return "\n".join(lines)

def key_to_name(key: str) -> str:
    for name in MENU_KEYS:
        if name.replace(" ", "_").replace("(", "").replace(")", "") == key:
            return name
    return None

# ─── ХЭНДЛЕРЫ ОФИЦИАНТА ──────────────────────────────────────
@waiter_dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.set_state(OrderState.choosing)
    await state.update_data(cart={})
    await message.answer(
        "🔥 *Шашлычная — Приём заказа*\n\nВыберите позиции из меню:",
        parse_mode="Markdown",
        reply_markup=menu_keyboard({})
    )

@waiter_dp.message(Command("new"))
async def cmd_new(message: types.Message, state: FSMContext):
    await state.set_state(OrderState.choosing)
    await state.update_data(cart={})
    await message.answer(
        "🆕 Новый заказ. Выберите позиции:",
        reply_markup=menu_keyboard({})
    )

@waiter_dp.callback_query(F.data.startswith("add_"))
async def cb_add_item(call: CallbackQuery, state: FSMContext):
    key = call.data[4:]
    name = key_to_name(key)
    if not name:
        await call.answer("Позиция не найдена")
        return
    data = await state.get_data()
    cart = data.get("cart", {})
    cart[name] = cart.get(name, 0) + 1
    await state.update_data(cart=cart)
    await call.message.edit_reply_markup(reply_markup=menu_keyboard(cart))
    await call.answer(f"+1 {name}")

@waiter_dp.callback_query(F.data == "clear")
async def cb_clear(call: CallbackQuery, state: FSMContext):
    await state.update_data(cart={})
    await call.message.edit_reply_markup(reply_markup=menu_keyboard({}))
    await call.answer("Корзина очищена")

@waiter_dp.callback_query(F.data == "checkout")
async def cb_checkout(call: CallbackQuery, state: FSMContext):
    await state.set_state(OrderState.table)
    await call.message.answer("📋 Введите номер стола:")
    await call.answer()

@waiter_dp.message(OrderState.table)
async def process_table(message: types.Message, state: FSMContext):
    global order_counter
    order_counter += 1
    order_id = order_counter

    data = await state.get_data()
    cart = data.get("cart", {})
    table = message.text.strip()
    time_str = datetime.now().strftime("%H:%M")

    # Сохраняем заказ
    orders[order_id] = {
        "cart": cart,
        "table": table,
        "waiter_chat": message.chat.id,
        "time": time_str,
    }

    text = format_order(cart, table, order_id, time_str)

    # Отправляем шашлычнику
    await cook_bot.send_message(
        COOK_CHAT_ID,
        text,
        parse_mode="Markdown",
        reply_markup=confirm_keyboard(order_id)
    )

    await message.answer(
        f"✅ Заказ #{order_id} отправлен шашлычнику!\n\nДля нового заказа нажми /new",
        parse_mode="Markdown"
    )
    await state.clear()

# ─── ХЭНДЛЕРЫ ШАШЛЫЧНИКА (через cook_bot) ───────────────────
cook_dp = Dispatcher(storage=MemoryStorage())

@cook_dp.callback_query(F.data.startswith("accept_"))
async def cook_accept(call: CallbackQuery):
    order_id = int(call.data.split("_")[1])
    order = orders.get(order_id)
    if not order:
        await call.answer("Заказ не найден")
        return

    await call.message.edit_text(
        call.message.text + "\n\n✅ *Принят в работу*",
        parse_mode="Markdown",
        reply_markup=ready_keyboard(order_id)
    )

    # Уведомляем официанта
    await waiter_bot.send_message(
        order["waiter_chat"],
        f"✅ Заказ *#{order_id}* принят шашлычником!",
        parse_mode="Markdown"
    )
    await call.answer("Принято!")

@cook_dp.callback_query(F.data.startswith("decline_"))
async def cook_decline(call: CallbackQuery):
    order_id = int(call.data.split("_")[1])
    order = orders.get(order_id)
    if not order:
        await call.answer("Заказ не найден")
        return

    await call.message.edit_text(
        call.message.text + "\n\n❌ *Отклонён*",
        parse_mode="Markdown"
    )

    await waiter_bot.send_message(
        order["waiter_chat"],
        f"❌ Заказ *#{order_id}* отклонён шашлычником.",
        parse_mode="Markdown"
    )
    await call.answer("Отклонено")

@cook_dp.callback_query(F.data.startswith("ready_"))
async def cook_ready(call: CallbackQuery):
    parts = call.data.split("_")
    order_id = int(parts[1])
    minutes  = int(parts[2])
    order = orders.get(order_id)
    if not order:
        await call.answer("Заказ не найден")
        return

    await call.message.edit_text(
        call.message.text + f"\n\n⏱ *Готовность через {minutes} мин*",
        parse_mode="Markdown"
    )

    await waiter_bot.send_message(
        order["waiter_chat"],
        f"⏱ Заказ *#{order_id}* будет готов через *{minutes} минут*!",
        parse_mode="Markdown"
    )
    await call.answer(f"Отправлено: {minutes} мин")

# ─── ЗАПУСК ──────────────────────────────────────────────────
async def main():
    await asyncio.gather(
        waiter_dp.start_polling(waiter_bot),
        cook_dp.start_polling(cook_bot),
    )

if __name__ == "__main__":
    asyncio.run(main())
