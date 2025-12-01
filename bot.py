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


# =================== DATA HANDLING ===================

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


# =================== MONEY PARSER ===================

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


# =================== UI MENU ===================

def send_menu(chat_id):
    buttons = [
        [InlineKeyboardButton("➕ Thêm quỹ", callback_data="add")],
        [InlineKeyboardButton("➖ Chi tiêu", callback_data="spend")],
        [InlineKeyboardButton("📊 Báo cáo", callback_data="report")],
    ]
    bot.send_message(chat_id, "📌 Chọn chức năng:", reply_markup=InlineKeyboardMarkup(buttons))


# =================== WEBHOOK ===================

@app.route("/", methods=["GET"])
def home():
    return "Bot đang hoạt động!"

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = telegram.Update.de_json(request.get_json(), bot)

    # ========== BUTTON HANDLING ==========
    if update.callback_query:
        chat_id = update.callback_query.message.chat_id
        action = update.callback_query.data

        state = load_state()
        state[str(chat_id)] = action
        save_state(state)

        if action == "add":
            bot.send_message(chat_id, "👉 Nhập số tiền cần nạp (vd: 500k hoặc 500k A nộp):")
        elif action == "spend":
            bot.send_message(chat_id, "👉 Nhập số tiền + ghi chú (vd: 50k rau, 200k thịt):")
        elif action == "report":
            data = load_data()
            now = datetime.datetime.now()
            current_month = now.strftime("%m")
            current_year = now.strftime("%Y")

            this_month_records = [
                r for r in data["lich_su"]
                if r["time"][5:7] == current_month and r["time"][0:4] == current_year
            ]

            total_add = sum(i["amount"] for i in this_month_records if i["type"] == "add")
            total_spend = sum(i["amount"] for i in this_month_records if i["type"] == "spend")

            report = f"📊 *BÁO CÁO THÁNG {current_month}/{current_year}*\n\n"

            report += f"💰 *Tổng nạp:* {format_money(total_add)}\n"
            for i in this_month_records:
                if i["type"] == "add":
                    report += f"   ➕ {format_money(i['amount'])} — {i['desc']}\n"

            report += "\n"

            report += f"🛍 *Tổng chi:* {format_money(total_spend)}\n"
            for i in this_month_records:
                if i["type"] == "spend":
                    report += f"   ➖ {format_money(i['amount'])} — {i['desc']}\n"

            report += "\n"
            report += f"💵 *Quỹ hiện tại:* {format_money(data['quy'])}"

            bot.send_message(chat_id, report, parse_mode="Markdown")

        return "OK"


    # ========== MESSAGE HANDLING ==========
    if update.message:
        chat_id = update.message.chat_id
        text = update.message.text
        user = update.message.from_user.first_name

        state = load_state()
        mode = state.get(str(chat_id))

        if text.startswith("/start"):
            send_menu(chat_id)
            return "OK"

        if not mode:
            bot.send_message(chat_id, "⚠️ Hãy chọn chức năng trước!")
            send_menu(chat_id)
            return "OK"

        data = load_data()

        # ========== ADD FUND ==========
        if mode == "add":
            parts = text.split(" ", 1)

            amount = parse_amount(parts[0])
            desc = parts[1] if len(parts) > 1 else "Nạp quỹ"
            desc = f"{desc} — ({user})"

            data["quy"] += amount
            data["lich_su"].append({
                "time": datetime.datetime.now().isoformat(),
                "type": "add",
                "amount": amount,
                "desc": desc,
                "user": user
            })
            save_data(data)

            bot.send_message(chat_id, f"💰 ĐÃ NẠP {format_money(amount)}\n🧾 {desc}\n👉 Quỹ: {format_money(data['quy'])}")

            state[str(chat_id)] = None
            save_state(state)
            send_menu(chat_id)
            return "OK"


        # ========== SPENDING ==========
        if mode == "spend":
            items = text.split(",")
            total = 0
            labels = []

            for item in items:
                part = item.strip().split(" ", 1)
                amount = parse_amount(part[0])
                desc = part[1] if len(part) > 1 else "Chi tiêu"
                desc = f"{desc} — ({user})"

                total += amount
                labels.append(desc)

                data["lich_su"].append({
                    "time": datetime.datetime.now().isoformat(),
                    "type": "spend",
                    "amount": amount,
                    "desc": desc,
                    "user": user
                })

            data["quy"] -= total
            save_data(data)

            # ===== RESET IF BALANCE = 0 =====
            if data["quy"] == 0:
                now = datetime.datetime.now()
                month = now.strftime("%m/%Y")

                total_add = sum(i["amount"] for i in data["lich_su"] if i["type"] == "add")
                total_spend = sum(i["amount"] for i in data["lich_su"] if i["type"] == "spend")

                summary_msg = (
                    f"📦 *KẾT THÚC CHU KỲ*\n\n"
                    f"🗓 Tháng: {month}\n\n"
                    f"💰 Tổng nạp: {format_money(total_add)}\n"
                    f"🛍 Tổng chi: {format_money(total_spend)}\n"
                    f"💵 Số dư cuối: {format_money(data['quy'])}\n\n"
                    f"📁 Dữ liệu đã được sao lưu.\n"
                    f"🔄 Quỹ = 0 → Bắt đầu chu kỳ mới."
                )

                bot.send_message(chat_id, summary_msg, parse_mode="Markdown")

                timestamp = now.strftime("%Y-%m-%d_%H-%M")
                filename = f"backup_{timestamp}.json"
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)

                data["lich_su"] = []
                save_data(data)

                send_menu(chat_id)
                return "OK"

            bot.send_message(chat_id, f"🧾 CHI {format_money(total)} — {', '.join(labels)}\n👉 Quỹ còn: {format_money(data['quy'])}")

            state[str(chat_id)] = None
            save_state(state)
            send_menu(chat_id)
            return "OK"

    return "OK"


if __name__ == "__main__":
    app.run()
