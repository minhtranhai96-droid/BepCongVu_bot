import os
import json
from datetime import datetime
import pytz
from flask import Flask, request
import telegram
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("BOT_TOKEN")
bot = telegram.Bot(token=TOKEN)

app = Flask(__name__)

DATA_FILE = "data.json"
STATE_FILE = "state.json"
VN_TIME = pytz.timezone("Asia/Ho_Chi_Minh")


# ================= FILE HANDLING =================

def load_data():
    return json.load(open(DATA_FILE, "r", encoding="utf-8")) if os.path.exists(DATA_FILE) else {"quy": 0, "lich_su": []}

def save_data(data):
    json.dump(data, open(DATA_FILE, "w", encoding="utf-8"), indent=4, ensure_ascii=False)

def load_state():
    return json.load(open(STATE_FILE, "r", encoding="utf-8")) if os.path.exists(STATE_FILE) else {}

def save_state(state):
    json.dump(state, open(STATE_FILE, "w", encoding="utf-8"), indent=4, ensure_ascii=False)


# ================= MONEY PARSING =================

def format_money(amount):
    amount = int(amount)
    if amount >= 1_000_000:
        return f"{amount/1_000_000:.1f}M".rstrip("0").rstrip(".")
    elif amount >= 1_000:
        return f"{amount//1000}k"
    return str(amount)

def parse_money(text):
    text = text.lower().replace(" ", "")
    if text.endswith("k"): return int(float(text[:-1]) * 1000)
    if text.endswith("m"): return int(float(text[:-1]) * 1_000_000)
    return int(text)


# ================= UI BUTTON MENU =================

def send_menu(chat_id):
    buttons = [
        [InlineKeyboardButton("➕ Thêm quỹ", callback_data="add_quy")],
        [InlineKeyboardButton("➖ Chi tiêu", callback_data="chi_tieu")],
        [InlineKeyboardButton("📊 Báo cáo", callback_data="baocao")],
    ]
    bot.send_message(chat_id, "Chọn chức năng:", reply_markup=InlineKeyboardMarkup(buttons))


# ================= WEBHOOK =================

@app.route("/", methods=["GET"])
def home():
    return "Bot đang chạy!"

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = telegram.Update.de_json(request.get_json(), bot)
    state = load_state()

    # ==== XỬ LÝ CALLBACK (NÚT BẤM) ====
    if update.callback_query:
        chat_id = update.callback_query.message.chat_id
        user = update.callback_query.from_user.first_name
        action = update.callback_query.data

        # Ghi trạng thái cho user
        if action == "add_quy":
            state[str(chat_id)] = "waiting_add"
            save_state(state)
            bot.send_message(chat_id, "Nhập số tiền nạp (vd: 500k, 1m, hoặc 500k Hải):")
            return "OK"

        elif action == "chi_tieu":
            state[str(chat_id)] = "waiting_spend"
            save_state(state)
            bot.send_message(chat_id, "Nhập số tiền + mô tả (vd: 50k rau, 200k gas):")
            return "OK"

        elif action == "baocao":
            data = load_data()
            msg = "📊 **BÁO CÁO**\n\n"
            msg += f"💰 Quỹ hiện tại: {format_money(data['quy'])}\n\n"

            for item in data["lich_su"][-10:]:
                msg += f"➡ {item['time']} | {item['user']} | {item['type']} | {format_money(item['amount'])} | {item['desc']}\n"

            bot.send_message(chat_id, msg, parse_mode="Markdown")
            return "OK"


    # ==== XỬ LÝ NHẬN TEXT ====
    if update.message:
        chat_id = update.message.chat_id
        txt = update.message.text
        user = update.message.from_user.first_name

        if txt.startswith("/start"):
            send_menu(chat_id)
            return "OK"

        mode = state.get(str(chat_id))  # user đang ở mục nào

        if not mode:
            bot.send_message(chat_id, "⚠ Vui lòng chọn chức năng trước:", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Thêm quỹ", callback_data="add_quy")],
                [InlineKeyboardButton("➖ Chi tiêu", callback_data="chi_tieu")]
            ]))
            return "OK"

        # ================= NẠP QUỸ =================
        if mode == "waiting_add":
            parts = txt.split(" ", 1)
            amount = parse_money(parts[0])
            desc = parts[1] if len(parts) > 1 else "Nạp quỹ"

            data = load_data()
            data["quy"] += amount
            data["lich_su"].append({
                "time": datetime.now(VN_TIME).strftime("%d/%m/%Y %H:%M"),
                "type": "add",
                "amount": amount,
                "desc": desc,
                "user": user
            })
            save_data(data)

            bot.send_message(chat_id, f"💰 ĐÃ NẠP {format_money(amount)} ({desc})\n👉 Quỹ còn: {format_money(data['quy'])}")
            state[str(chat_id)] = None
            save_state(state)
            return "OK"

        # ================= CHI TIÊU =================
        if mode == "waiting_spend":
            parts = txt.split(" ", 1)
            if len(parts) < 2:
                bot.send_message(chat_id, "⚠ Nhập đúng định dạng: `50k rau`")
                return "OK"

            amount = parse_money(parts[0])
            desc = parts[1]

            data = load_data()
            data["quy"] -= amount
            data["lich_su"].append({
                "time": datetime.now(VN_TIME).strftime("%d/%m/%Y %H:%M"),
                "type": "spend",
                "amount": amount,
                "desc": desc,
                "user": user
            })
            save_data(data)

            bot.send_message(chat_id, f"🧾 CHI: {format_money(amount)} — {desc}\n👉 Quỹ còn: {format_money(data['quy'])}")
            state[str(chat_id)] = None
            save_state(state)
            return "OK"

    return "OK"
