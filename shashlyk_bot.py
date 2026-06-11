import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
import threading

WAITER_TOKEN = "8851091659:AAFDcVFsFH9hyhRcQivsHoeQmiRzzvomoX0"
COOK_TOKEN = "8995232402:AAFTllVg6BnpV241DEQQfkg9pGChanUFroI"
COOK_CHAT_ID = 853166810

MENU = {
    "chicken_thigh":   ("🍗 Куриное бедро",     2900),
    "chicken_fillet":  ("🍗 Курица филе",        3000),
    "chicken_wings":   ("🍗 Куриные крылья",     2800),
    "lamb":            ("🐑 Баранина",            4000),
    "pork":            ("🐷 Свинина",             3600),
    "duck":            ("🦆 Утка",                3200),
    "mushrooms":       ("🍄 Грибы",               2000),
    "sausage_dacha":   ("🌭 Дачные сосиски",      1500),
    "sausage_mexico":  ("🌭 Мексика",             1500),
    "sausage_village": ("🌭 Деревенские",         1500),
    "sausage_gourmet": ("🌭 Гурман",              1500),
    "sausage_chicken": ("🌭 Куриные сосиски",     1500),
    "veggies":         ("🥦 Овощи на гриле",      1800),
    "tench":           ("🐟 Линь с овощами",      3500),
    "carp":            ("🐟 Карась во фритюре",   2500),
}

orders = {}
order_counter = [0]
user_carts = {}
user_state = {}  # "choosing" or "table"

waiter_bot = telebot.TeleBot(WAITER_TOKEN)
cook_bot   = telebot.TeleBot(COOK_TOKEN)

def menu_keyboard(cart):
    kb = InlineKeyboardMarkup()
    for key, (name, price) in MENU.items():
        qty = cart.get(key, 0)
        if qty > 0:
            label = f"✅ {name} x{qty} — {price*qty}₸"
        else:
            label = f"{name} — {price}₸"
        kb.add(InlineKeyboardButton(label, callback_data=f"add_{key}"))
    total = sum(MENU[k][1]*q for k,q in cart.items())
    if total > 0:
        kb.add(InlineKeyboardButton(f"🛒 Оформить — итого {total}₸", callback_data="checkout"))
        kb.add(InlineKeyboardButton("🗑 Очистить", callback_data="clear"))
    return kb

def confirm_keyboard(order_id):
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("✅ Принял", callback_data=f"accept_{order_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"decline_{order_id}")
    )
    return kb

def ready_keyboard(order_id):
    kb = InlineKeyboardMarkup()
    kb.row(*[InlineKeyboardButton(f"⏱{t}м", callback_data=f"ready_{order_id}_{t}") for t in [10,15,20,30,45]])
    return kb

def format_order(cart, table, order_id, time_str):
    lines = [f"🔥 *ЗАКАЗ #{order_id}* — стол *{table}*", f"🕐 {time_str}", "─────────────────"]
    total = 0
    for key, qty in cart.items():
        name, price = MENU[key]
        subtotal = price * qty
        total += subtotal
        lines.append(f"• {name} × {qty} — {subtotal}₸")
    lines += ["─────────────────", f"💰 *Итого: {total}₸*"]
    return "\n".join(lines)

# ── WAITER BOT ──
@waiter_bot.message_handler(commands=["start", "new"])
def cmd_start(msg):
    user_carts[msg.chat.id] = {}
    user_state[msg.chat.id] = "choosing"
    waiter_bot.send_message(msg.chat.id, "🔥 *Шашлычная — Приём заказа*\n\nВыберите позиции:",
                            parse_mode="Markdown", reply_markup=menu_keyboard({}))

@waiter_bot.callback_query_handler(func=lambda c: c.data.startswith("add_"))
def cb_add(call):
    key = call.data[4:]
    cart = user_carts.get(call.message.chat.id, {})
    cart[key] = cart.get(key, 0) + 1
    user_carts[call.message.chat.id] = cart
    waiter_bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=menu_keyboard(cart))
    waiter_bot.answer_callback_query(call.id, f"+1 {MENU[key][0]}")

@waiter_bot.callback_query_handler(func=lambda c: c.data == "clear")
def cb_clear(call):
    user_carts[call.message.chat.id] = {}
    waiter_bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=menu_keyboard({}))
    waiter_bot.answer_callback_query(call.id, "Очищено")

@waiter_bot.callback_query_handler(func=lambda c: c.data == "checkout")
def cb_checkout(call):
    user_state[call.message.chat.id] = "table"
    waiter_bot.answer_callback_query(call.id)
    waiter_bot.send_message(call.message.chat.id, "📋 Введите номер стола:")

@waiter_bot.message_handler(func=lambda m: user_state.get(m.chat.id) == "table")
def process_table(msg):
    order_counter[0] += 1
    oid = order_counter[0]
    cart = user_carts.get(msg.chat.id, {})
    table = msg.text.strip()
    time_str = datetime.now().strftime("%H:%M")
    orders[oid] = {"cart": cart, "table": table, "waiter_chat": msg.chat.id, "time": time_str}
    text = format_order(cart, table, oid, time_str)
    cook_bot.send_message(COOK_CHAT_ID, text, parse_mode="Markdown", reply_markup=confirm_keyboard(oid))
    waiter_bot.send_message(msg.chat.id, f"✅ Заказ #{oid} отправлен шашлычнику!\n\nНовый заказ: /new", parse_mode="Markdown")
    user_state[msg.chat.id] = "choosing"

# ── COOK BOT ──
@cook_bot.callback_query_handler(func=lambda c: c.data.startswith("accept_"))
def cook_accept(call):
    oid = int(call.data.split("_")[1])
    order = orders.get(oid)
    if not order: return
    cook_bot.edit_message_text(call.message.text + "\n\n✅ *Принят в работу*",
                               call.message.chat.id, call.message.message_id,
                               parse_mode="Markdown", reply_markup=ready_keyboard(oid))
    waiter_bot.send_message(order["waiter_chat"], f"✅ Заказ *#{oid}* принят шашлычником!", parse_mode="Markdown")
    cook_bot.answer_callback_query(call.id, "Принято!")

@cook_bot.callback_query_handler(func=lambda c: c.data.startswith("decline_"))
def cook_decline(call):
    oid = int(call.data.split("_")[1])
    order = orders.get(oid)
    if not order: return
    cook_bot.edit_message_text(call.message.text + "\n\n❌ *Отклонён*",
                               call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    waiter_bot.send_message(order["waiter_chat"], f"❌ Заказ *#{oid}* отклонён.", parse_mode="Markdown")
    cook_bot.answer_callback_query(call.id)

@cook_bot.callback_query_handler(func=lambda c: c.data.startswith("ready_"))
def cook_ready(call):
    parts = call.data.split("_")
    oid, mins = int(parts[1]), int(parts[2])
    order = orders.get(oid)
    if not order: return
    cook_bot.edit_message_text(call.message.text + f"\n\n⏱ *Готовность через {mins} мин*",
                               call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    waiter_bot.send_message(order["waiter_chat"], f"⏱ Заказ *#{oid}* будет готов через *{mins} минут*!", parse_mode="Markdown")
    cook_bot.answer_callback_query(call.id, f"{mins} мин")

# ── RUN ──
t1 = threading.Thread(target=waiter_bot.infinity_polling)
t2 = threading.Thread(target=cook_bot.infinity_polling)
t1.start()
t2.start()
t1.join()
t2.join()
