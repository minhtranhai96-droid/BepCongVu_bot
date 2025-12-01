import os
import json
import datetime
from flask import Flask, request
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

TOKEN = os.getenv("BOT_TOKEN")
bot = telegram.Bot(token=TOKEN)

app = Flask(__name__)

DATA_FILE = "data.json"
STATE_FILE = "state.json"


def load_data():
    if not os.path.exists(DATA_FILE):
        return {"quy": 0, "lich_su": []}
    return json.load(open(DATA_FILE, "r", encoding="utf-8"))


def save_data(data):
    json.dump(data, open(DATA_FILE, "w", encoding="utf-8"), indent=4, ensure_ascii=False)


def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    return json.load(open(STATE_FILE, "r", encoding="utf-8"))


def save_state(state):
    json.dump(state, open(STATE_FILE, "w", encoding="utf-8"), indent=4)


def format_money(amount):
    amount = int(amount)
    if amount >= 1_000_000:
        return f"{amount//1_000_000}m"
    if amount >= 1_000:
        return f"{amount//1000}k"
    return str(amount)


def parse_amount(text):
    text = text.lower().replace(" ", "")
    if text.endswith("k"):
        return int(text[:-1]) * 1000
    if text.endswith("m"):
        return int(text[:-1]) * 1_000_000
    return int(text)


def send_menu(chat_id):
    buttons = [
        [InlineKeyboardButton("➕ Thêm quỹ", callback_data="add")],
        [InlineKeyboardButton("➖ Chi tiêu", callback_data="spend")],
        [InlineKeyboardButton("📊 Báo cáo", callback_data="report")],
    ]
    bot.send_message(chat_id, "Chọn chức năng:", reply_markup=InlineKeyboardMarkup(buttons))


@app.route("/", methods=["GET"])
def home():
    return "Bot đang hoạt động!"


@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = telegram.Update.de_json(request.get_json(), bot)

    if update.callback_query:
        chat_id = update.callback_query.message.chat_id
        user = update.callback_query.from_user.first_name
        action = update.callback_query.data

        state = load_state()
        state[str(chat_id)] = action
        save_state(state)

        if action == "add":
            bot.send_message(chat_id, "👉 Nhập số tiền nạp (ví dụ: `500k A Phúc`):")
        elif action == "spend":
            bot.send_message(chat_id, "👉 Nhập số tiền + mô tả (ví dụ: `50k rau, 200k thịt`):")
        elif action == "report":
            data = load_data()
            total_add = sum(i["amount"] for i in data["lich_su"] if i["type"] == "add")
            total_spend = sum(i["amount"] for i in data["lich_su"] if i["type"] == "spend")

            msg = f"""
📊 BÁO CÁO TỔNG HỢP

💰 Tổng nạp: {format_money(total_add)}
🛒 Tổng chi: {format_money(total_spend)}

💵 Quỹ còn lại: {format_money(data['quy'])}
"""
            bot.send_message(chat_id, msg.strip())
        return "OK"

    if update.message:
        chat_id = update.message.chat_id
        text = update.message.text
        user = update.message.from_user.first_name

        state = load_state()
        mode = state.get(str(chat_id))

        if not mode:
            bot.send_message(chat_id, "⚠️ Vui lòng chọn chức năng trước:")
            send_menu(chat_id)
            return "OK"

        data = load_data()

        if mode == "add":
            parts = text.split(" ", 1)
            amount = parse_amount(parts[0])
            desc = parts[1] if len(parts) > 1 else user

            data["quy"] += amount
            data["lich_su"].append({
                "time": datetime.datetime.utcnow().isoformat(),
                "type": "add",
                "amount": amount,
                "desc": desc,
                "user": user
            })
            save_data(data)

            bot.send_message(chat_id, f"💰 ĐÃ NẠP {format_money(amount)} ({desc})\n👉 Quỹ: {format_money(data['quy'])}")
            send_menu(chat_id)
            return "OK"

        if mode == "spend":
            items = text.split(",")
            total = 0
            details = []

            for item in items:
                part = item.strip().split(" ", 1)
                amount = parse_amount(part[0])
                desc = part[1] if len(part) > 1 else ""

                total += amount
                details.append(desc)

                data["lich_su"].append({
                    "time": datetime.datetime.utcnow().isoformat(),
                    "type": "spend",
                    "amount": amount,
                    "desc": desc,
                    "user": user
                })

            data["quy"] -= total
            save_data(data)

            bot.send_message(chat_id, f"🧾 CHI: {format_money(total)} — {', '.join(details)}\n👉 Quỹ còn: {format_money(data['quy'])}")
            send_menu(chat_id)

    return "OK"


if __name__ == "__main__":
    app.run()
