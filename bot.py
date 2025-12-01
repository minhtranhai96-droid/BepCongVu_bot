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
MSG_FILE = "messages.json"


# =================== FILE HANDLERS ===================

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

def load_messages():
    if not os.path.exists(MSG_FILE):
        return []
    return json.load(open(MSG_FILE, "r", encoding="utf-8"))

def save_messages(msgs):
    json.dump(msgs, open(MSG_FILE, "w", encoding="utf-8"), indent=4)


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
    return None


# =================== SEND + LOG MESSAGE ===================

def send_and_log(chat_id, text, **kwargs):
    msg = bot.send_message(chat_id, text, **kwargs)
    msgs = load_messages()
    msgs.append({"chat_id": chat_id, "msg_id": msg.message_id})
    save_messages(msgs)
    return msg


# =================== MENU ===================

def send_menu(chat_id):
    buttons = [
        [InlineKeyboardButton("➕ Thêm quỹ", callback_data="add")],
        [InlineKeyboardButton("➖ Chi tiêu", callback_data="spend")],
        [InlineKeyboardButton("📊 Báo cáo", callback_data="report")],
        [InlineKeyboardButton("🔙 Hoàn tác giao dịch cuối", callback_data="undo")],
        [InlineKeyboardButton("🧹 Xóa tin bot", callback_data="clear")]
    ]
    send_and_log(chat_id, "📌 Chọn chức năng:", reply_markup=InlineKeyboardMarkup(buttons))


# =================== WEBHOOK ===================

@app.route("/", methods=["GET"])
def home():
    return "Bot đang hoạt động!"

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = telegram.Update.de_json(request.get_json(), bot)

    # ================= CALLBACK BUTTON ACTIONS =================
    if update.callback_query:
        chat_id = update.callback_query.message.chat_id
        user = update.callback_query.from_user.first_name
        action = update.callback_query.data

        data = load_data()
        state = load_state()
        messages = load_messages()

        state[str(chat_id)] = action
        save_state(state)

        # ---- UNDO ----
        if action == "undo":
            if not data["lich_su"]:
                send_and_log(chat_id, "⚠️ Không có giao dịch nào để hoàn tác.")
                return "OK"

            last = data["lich_su"][-1]
            if last["user"] != user:
                send_and_log(chat_id, "⛔ Bạn không thể hoàn tác giao dịch của người khác.")
                return "OK"

            removed = data["lich_su"].pop()

            if removed["type"] == "add":
                data["quy"] -= removed["amount"]
            else:
                data["quy"] += removed["amount"]

            save_data(data)

            send_and_log(chat_id, f"🗑 HOÀN TÁC: {format_money(removed['amount'])} — {removed['desc']}\n💵 Quỹ mới: {format_money(data['quy'])}")
            send_menu(chat_id)
            return "OK"

        # ---- CLEAR MESSAGES (ADMIN ONLY) ----
        if action == "clear":
            try:
                member = bot.get_chat_member(chat_id, update.callback_query.from_user.id)
            except:
                send_and_log(chat_id, "⚠️ Không xác định được quyền.")
                return "OK"

            if member.status not in ["administrator", "creator"]:
                send_and_log(chat_id, "⛔ Chỉ quản trị viên mới được dùng chức năng này.")
                return "OK"

            deleted = 0
            for msg in messages:
                try:
                    bot.delete_message(msg["chat_id"], msg["msg_id"])
                    deleted += 1
                except:
                    pass

            save_messages([])

            send_and_log(chat_id, f"🧹 Đã xoá {deleted} tin nhắn bot. (Không mất lịch sử quỹ)")
            send_menu(chat_id)
            return "OK"

        # ---- NORMAL BUTTONS ----
        if action == "add":
            send_and_log(chat_id, "👉 Nhập tiền nạp (vd: 100k hoặc 300k A nộp):")

        elif action == "spend":
            send_and_log(chat_id, "👉 Nhập chi tiêu (vd: 50k rau, 200k thịt):")

        elif action == "report":
            now = datetime.datetime.now(TZ)
            month = now.strftime("%m")
            year = now.strftime("%Y")

            filtered = [r for r in data["lich_su"] if r["time"][5:7] == month and r["time"][0:4] == year]

            total_add = sum(x["amount"] for x in filtered if x["type"] == "add")
            total_spend = sum(x["amount"] for x in filtered if x["type"] == "spend")

            msg = f"📊 *BÁO CÁO THÁNG {month}/{year}*\n\n💰 Tổng nạp: {format_money(total_add)}\n"

            for i in filtered:
                t = datetime.datetime.strptime(i["time"], "%Y-%m-%d %H:%M:%S").strftime("%d/%m %H:%M")
                symbol = "➕" if i["type"] == "add" else "➖"
                msg += f"   {symbol} {format_money(i['amount'])} — {i['desc']} • {t}\n"

            msg += f"\n💵 *Quỹ hiện tại:* {format_money(data['quy'])}"

            send_and_log(chat_id, msg, parse_mode="Markdown")

        return "OK"


    # ================= MESSAGE INPUT MODE =================
    if update.message:
        chat_id = update.message.chat_id
        user = update.message.from_user.first_name
        text = update.message.text

        data = load_data()
        state = load_state()

        if text.startswith("/start"):
            send_menu(chat_id)
            return "OK"

        mode = state.get(str(chat_id))

        if not mode:
            send_and_log(chat_id, "⚠️ Hãy chọn chức năng trước!")
            send_menu(chat_id)
            return "OK"

        # ===== ADD MONEY =====
        if mode == "add":
            token = text.split(" ", 1)[0].lower()
            amount = parse_amount(token)

            if amount is None:
                send_and_log(chat_id, "❌ Sai cú pháp!\n💡 Ví dụ đúng:\n- 100k\n- 200k A nộp\n👉 Nhập lại:")
                return "OK"

            desc = text[len(token):].strip() or "Nạp quỹ"
            desc = f"{desc} — ({user})"

            data["quy"] += amount
            data["lich_su"].append({"time": now_time(), "type": "add", "amount": amount, "desc": desc, "user": user})
            save_data(data)

            send_and_log(chat_id, f"💰 NẠP {format_money(amount)}\n🧾 {desc}\n👉 Quỹ: {format_money(data['quy'])}")

            state[str(chat_id)] = None
            save_state(state)
            send_menu(chat_id)
            return "OK"

        # ===== SPENDING =====
        if mode == "spend":
            entries = text.split(",")
            total = 0
            items = []

            for entry in entries:
                part = entry.strip().split(" ", 1)
                token = part[0].lower()
                amount = parse_amount(token)

                if amount is None:
                    send_and_log(chat_id, "❌ Sai cú pháp!\n💡 Ví dụ đúng:\n- 50k rau\n- 50k rau, 200k thịt\n👉 Nhập lại:")
                    return "OK"

                desc = part[1] if len(part) > 1 else "Chi tiêu"
                desc = f"{desc} — ({user})"

                total += amount
                items.append({"amount": amount, "desc": desc})

            for x in items:
                data["lich_su"].append({"time": now_time(), "type": "spend", "amount": x["amount"], "desc": x["desc"], "user": user})

            data["quy"] -= total
            save_data(data)

            # ---- Reset if zero ----
            if data["quy"] == 0:
                now = datetime.datetime.now(TZ)
                summary = f"📦 Chu kỳ đã kết thúc!\n📁 Backup đã lưu.\n🔄 Bắt đầu chu kỳ mới."
                send_and_log(chat_id, summary)

                backup = f"backup_{now.strftime('%Y%m%d_%H%M')}.json"
                json.dump(data, open(backup, "w", encoding="utf-8"), indent=4)

                data["lich_su"] = []
                save_data(data)

                send_menu(chat_id)
                return "OK"

            send_and_log(chat_id, f"🧾 CHI {format_money(total)} thành công!\n👉 Quỹ còn: {format_money(data['quy'])}")

            state[str(chat_id)] = None
            save_state(state)
            send_menu(chat_id)
            return "OK"

    return "OK"


if __name__ == "__main__":
    app.run()
