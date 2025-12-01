import os
import json
import datetime
from flask import Flask, request
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import pytz

# ==== TIMEZONE FIX ====
TZ = pytz.timezone("Asia/Ho_Chi_Minh")

def now_time():
    return datetime.datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


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


# =================== MONEY FORMAT ===================

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
    return None  # INVALID if no k/m suffix


# =================== MENU ===================

def send_menu(chat_id):
    buttons = [
        [InlineKeyboardButton("➕ Thêm quỹ", callback_data="add")],
        [InlineKeyboardButton("➖ Chi tiêu", callback_data="spend")],
        [InlineKeyboardButton("📊 Báo cáo", callback_data="report")],
        [InlineKeyboardButton("🔙 Hoàn tác giao dịch cuối", callback_data="undo")]
    ]
    bot.send_message(chat_id, "📌 Chọn chức năng:", reply_markup=InlineKeyboardMarkup(buttons))


# =================== WEBHOOK ===================

@app.route("/", methods=["GET"])
def home():
    return "Bot đang hoạt động!"

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = telegram.Update.de_json(request.get_json(), bot)

    # ====== CALLBACK BUTTON ======
    if update.callback_query:
        chat_id = update.callback_query.message.chat_id
        action = update.callback_query.data
        user = update.callback_query.from_user.first_name

        data = load_data()
        state = load_state()

        state[str(chat_id)] = action
        save_state(state)

        # ---- Undo Logic ----
        if action == "undo":
            if not data["lich_su"]:
                bot.send_message(chat_id, "⚠️ Không có giao dịch nào để hoàn tác.")
                return "OK"

            last = data["lich_su"][-1]

            if last["user"] != user:
                bot.send_message(chat_id, "⛔ Bạn không thể hoàn tác giao dịch của người khác.")
                return "OK"

            removed = data["lich_su"].pop()

            if removed["type"] == "add":
                data["quy"] -= removed["amount"]
            else:
                data["quy"] += removed["amount"]

            save_data(data)

            bot.send_message(chat_id, f"🗑 HOÀN TÁC: {format_money(removed['amount'])} — {removed['desc']}\n💵 Quỹ mới: {format_money(data['quy'])}")
            send_menu(chat_id)
            return "OK"

        # Normal menu actions
        if action == "add":
            bot.send_message(chat_id, "👉 Nhập tiền nạp (vd: 100k hoặc 300k A nộp):")
        elif action == "spend":
            bot.send_message(chat_id, "👉 Nhập chi tiêu (vd: 50k rau, 200k thịt):")
        elif action == "report":
            now = datetime.datetime.now(TZ)
            month = now.strftime("%m")
            year = now.strftime("%Y")

            records = [
                r for r in data["lich_su"]
                if r["time"][5:7] == month and r["time"][0:4] == year
            ]

            total_add = sum(i["amount"] for i in records if i["type"] == "add")
            total_spend = sum(i["amount"] for i in records if i["type"] == "spend")

            msg = f"📊 *BÁO CÁO THÁNG {month}/{year}*\n\n💰 Tổng nạp: {format_money(total_add)}\n"
            for i in records:
                if i["type"] == "add":
                    t = datetime.datetime.strptime(i["time"], "%Y-%m-%d %H:%M:%S").strftime("%d/%m %H:%M")
                    msg += f"   ➕ {format_money(i['amount'])} — {i['desc']} • {t}\n"

            msg += f"\n🛍 Tổng chi: {format_money(total_spend)}\n"
            for i in records:
                if i["type"] == "spend":
                    t = datetime.datetime.strptime(i["time"], "%Y-%m-%d %H:%M:%S").strftime("%d/%m %H:%M")
                    msg += f"   ➖ {format_money(i['amount'])} — {i['desc']} • {t}\n"

            msg += f"\n💵 *Quỹ hiện tại:* {format_money(data['quy'])}"

            bot.send_message(chat_id, msg, parse_mode="Markdown")

        return "OK"


    # ====== MESSAGE INPUT MODE ======
    if update.message:
        chat_id = update.message.chat_id
        text = update.message.text
        user = update.message.from_user.first_name

        state = load_state()
        mode = state.get(str(chat_id))
        data = load_data()

        if text.startswith("/start"):
            send_menu(chat_id)
            return "OK"

        if not mode:
            bot.send_message(chat_id, "⚠️ Hãy chọn chức năng trước!")
            send_menu(chat_id)
            return "OK"

        # ========= ADD MONEY =========
        if mode == "add":
            token = text.split(" ", 1)[0].lower()
            amount = parse_amount(token)

            if amount is None:
                bot.send_message(chat_id, "❌ Sai định dạng!\n💡 Ví dụ đúng:\n• 50k\n• 300k A nộp\n\n👉 Nhập lại:")
                return "OK"

            desc = text[len(token):].strip() or "Nạp quỹ"
            desc = f"{desc} — ({user})"

            data["quy"] += amount
            data["lich_su"].append({
                "time": now_time(),
                "type": "add",
                "amount": amount,
                "desc": desc,
                "user": user
            })
            save_data(data)

            bot.send_message(chat_id, f"💰 NẠP {format_money(amount)}\n🧾 {desc}\n👉 Quỹ: {format_money(data['quy'])}")

            state[str(chat_id)] = None
            save_state(state)
            send_menu(chat_id)
            return "OK"


        # ========= SPENDING =========
        if mode == "spend":
            items = text.split(",")
            total = 0
            records = []

            for item in items:
                part = item.strip().split(" ", 1)
                token = part[0].lower()
                amount = parse_amount(token)

                if amount is None:
                    bot.send_message(chat_id, "❌ Sai định dạng!\n💡 Ví dụ đúng:\n• 50k rau\n• 50k rau, 200k thịt\n\n👉 Nhập lại toàn bộ:")
                    return "OK"

                desc = part[1] if len(part) > 1 else "Chi tiêu"
                desc = f"{desc} — ({user})"

                total += amount
                records.append({"amount": amount, "desc": desc})

            # apply
            for r in records:
                data["lich_su"].append({
                    "time": now_time(),
                    "type": "spend",
                    "amount": r["amount"],
                    "desc": r["desc"],
                    "user": user
                })

            data["quy"] -= total
            save_data(data)

            # === RESET WHEN FUNDS = 0 ===
            if data["quy"] == 0:
                now = datetime.datetime.now(TZ)
                month = now.strftime("%m/%Y")

                total_add = sum(i["amount"] for i in data["lich_su"] if i["type"] == "add")
                total_spend = sum(i["amount"] for i in data["lich_su"] if i["type"] == "spend")

                msg = (
                    f"📦 *KẾT THÚC CHU KỲ*\n\n"
                    f"🗓 Tháng: {month}\n\n"
                    f"💰 Tổng nạp: {format_money(total_add)}\n"
                    f"🛍 Tổng chi: {format_money(total_spend)}\n"
                    f"💵 Số dư cuối: 0\n\n"
                    f"📁 Đã lưu backup.\n"
                    f"🔄 Bắt đầu chu kỳ mới."
                )

                bot.send_message(chat_id, msg, parse_mode="Markdown")

                timestamp = now.strftime("%Y-%m-%d_%H-%M")
                backup = f"backup_{timestamp}.json"
                json.dump(data, open(backup, "w", encoding="utf-8"), indent=4, ensure_ascii=False)

                data["lich_su"] = []
                save_data(data)
                send_menu(chat_id)
                return "OK"

            bot.send_message(chat_id, f"🧾 CHI {format_money(total)} — cập nhật!\n👉 Quỹ còn: {format_money(data['quy'])}")

            state[str(chat_id)] = None
            save_state(state)
            send_menu(chat_id)
            return "OK"

    return "OK"


if __name__ == "__main__":
    app.run()
