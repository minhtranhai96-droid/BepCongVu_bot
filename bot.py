import os
import json
import datetime
from flask import Flask, request
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# =========================================
# CONFIG
# =========================================
TOKEN = os.getenv("BOT_TOKEN")
bot = telegram.Bot(TOKEN)

DATA_FILE = "data.json"

ADMIN_IDS = {977170999}   # ID admin của bạn

STATE = {}  # Lưu trạng thái người dùng theo chat_id

app = Flask(__name__)


# =========================================
# HÀM FORMAT TIỀN
# =========================================
def format_money(amount):
    amount = int(amount)
    return f"{amount // 1000}k"


# =========================================
# PARSE SỐ TIỀN USER NHẬP
# =========================================
def parse_amount(text):
    text = text.strip().lower()

    if text.endswith("k"):
        num = text[:-1]
        if num.isdigit():
            return int(num) * 1000
        return None

    if text.isdigit():
        return int(text)

    return None


# =========================================
# TIME GMT+7
# =========================================
def now():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%d/%m/%Y %H:%M")


# =========================================
# LOAD / SAVE
# =========================================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "quy": 0,
            "quy_tools": 0,
            "lich_su": [],
            "lich_su_tools": [],
            "last_action": None
        }
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(db):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4, ensure_ascii=False)


# =========================================
# MENU
# =========================================
def send_menu(chat_id):
    buttons = [
        [InlineKeyboardButton("➕ Thêm quỹ", callback_data="add_quy")],
        [InlineKeyboardButton("➖ Chi tiêu", callback_data="spend")],
        [InlineKeyboardButton("🛠 Thêm quỹ dụng cụ", callback_data="add_tool")],
        [InlineKeyboardButton("🛠 Chi dụng cụ", callback_data="spend_tool")],
        [InlineKeyboardButton("📊 Báo cáo", callback_data="report")],
        [InlineKeyboardButton("↩ Hoàn tác giao dịch", callback_data="undo")]
    ]
    bot.send_message(chat_id, "📌 *Chọn chức năng:*", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


# =========================================
# WEBHOOK ROOT
# =========================================
@app.route("/", methods=["GET"])
def home():
    return "Bot is running!"


# =========================================
# WEBHOOK MAIN
# =========================================
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = telegram.Update.de_json(request.get_json(force=True), bot)

    # ======================================================
    # XỬ LÝ CALLBACK BUTTON
    # ======================================================
    if update.callback_query:
        cq = update.callback_query
        chat_id = cq.message.chat_id
        user_id = cq.from_user.id
        key = cq.data

        # LƯU TRẠNG THÁI
        STATE[chat_id] = key

        # Kiểm tra quyền admin cho chức năng đặc biệt
        if key in ["add_tool", "spend_tool"]:
            if user_id not in ADMIN_IDS:
                bot.send_message(chat_id, "⛔ Chỉ admin mới được dùng chức năng này.")
                return "OK"

        messages = {
            "add_quy": "👉 Nhập số tiền nạp (vd: 100k hoặc 300k A nộp):",
            "spend": "👉 Nhập số tiền + mô tả (vd: 50k rau):",
            "add_tool": "👉 Nhập số tiền nạp quỹ dụng cụ:",
            "spend_tool": "👉 Nhập số tiền + mô tả dụng cụ (vd: 40k dao):"
        }

        if key in messages:
            bot.send_message(chat_id, messages[key])
            return "OK"

        # =========== HOÀN TÁC ===========
        if key == "undo":
            db = load_data()

            if not db["last_action"]:
                bot.send_message(chat_id, "⚠ Không có giao dịch để hoàn tác.")
                return "OK"

            act = db["last_action"]
            t = act["type"]
            amount = act["amount"]

            if t == "add":
                db["quy"] -= amount
                db["lich_su"].pop()

            if t == "spend":
                db["quy"] += amount
                db["lich_su"].pop()

            if t == "add_tool":
                db["quy_tools"] -= amount
                db["lich_su_tools"].pop()

            if t == "spend_tool":
                db["quy_tools"] += amount
                db["lich_su_tools"].pop()

            db["last_action"] = None
            save_data(db)

            bot.send_message(chat_id, "↩ Đã hoàn tác giao dịch cuối.")
            return "OK"

        # =========== BÁO CÁO ===========
        if key == "report":
            db = load_data()

            text = f"📊 *BÁO CÁO THÁNG {now()[3:10]}*\n\n"

            # --- QUỸ CHÍNH ---
            text += "💰 *QUỸ CHÍNH*\n"
            total_add = sum(i["amount"] for i in db["lich_su"] if i["kind"] == "add")
            total_spend = sum(i["amount"] for i in db["lich_su"] if i["kind"] == "spend")

            text += f"• Tổng nạp: {format_money(total_add)}\n"
            text += f"• Tổng chi: {format_money(total_spend)}\n"
            text += f"• Còn lại: {format_money(db['quy'])}\n\n"

            # --- Lịch sử ---
            for i in db["lich_su"]:
                op = "➕" if i["kind"] == "add" else "➖"
                text += f"{op} {format_money(i['amount'])} — {i['desc']} • {i['time']}\n"

            text += "\n\n🛠 *QUỸ DỤNG CỤ*\n"
            total_add2 = sum(i["amount"] for i in db["lich_su_tools"] if i["kind"] == "add")
            total_spend2 = sum(i["amount"] for i in db["lich_su_tools"] if i["kind"] == "spend")

            text += f"• Tổng nạp: {format_money(total_add2)}\n"
            text += f"• Tổng chi: {format_money(total_spend2)}\n"
            text += f"• Còn lại: {format_money(db['quy_tools'])}\n\n"

            for i in db["lich_su_tools"]:
                op = "➕" if i["kind"] == "add" else "➖"
                text += f"{op} {format_money(i['amount'])} — {i['desc']} • {i['time']}\n"

            bot.send_message(chat_id, text, parse_mode="Markdown")
            return "OK"

    # ======================================================
    # XỬ LÝ TIN NHẮN (NHẬP SỐ TIỀN...)
    # ======================================================
    if update.message:
        msg = update.message
        chat_id = msg.chat_id
        text = msg.text.strip()
        user = msg.from_user.first_name

        if text.startswith("/start"):
            send_menu(chat_id)
            return "OK"

        if chat_id not in STATE:
            bot.send_message(chat_id, "⚠ Vui lòng chọn chức năng trước.")
            send_menu(chat_id)
            return "OK"

        mode = STATE[chat_id]
        db = load_data()

        # ==== NẠP QUỸ CHÍNH ====
        if mode == "add_quy":
            parts = text.split(" ", 1)
            amount = parse_amount(parts[0])

            if amount is None:
                bot.send_message(chat_id, "⚠ Sai cú pháp! Ví dụ đúng: 100k hoặc 300k A nộp")
                return "OK"

            desc = parts[1] if len(parts) > 1 else f"Nạp quỹ — ({user})"

            db["quy"] += amount
            db["lich_su"].append({
                "time": now(),
                "kind": "add",
                "amount": amount,
                "desc": desc,
                "user": user
            })
            db["last_action"] = {"type": "add", "amount": amount}
            save_data(db)

            bot.send_message(chat_id, f"💰 NẠP {format_money(amount)}\n👉 Quỹ: {format_money(db['quy'])}")
            STATE.pop(chat_id)
            return "OK"

        # ==== CHI QUỸ CHÍNH ====
        if mode == "spend":
            parts = text.split(" ", 1)

            if len(parts) < 2:
                bot.send_message(chat_id, "⚠ Sai cú pháp! Ví dụ: 30k rau")
                return "OK"

            amount = parse_amount(parts[0])
            if amount is None:
                bot.send_message(chat_id, "⚠ Sai số tiền! Ví dụ: 50k")
                return "OK"

            desc = parts[1] + f" — ({user})"

            db["quy"] -= amount
            db["lich_su"].append({
                "time": now(),
                "kind": "spend",
                "amount": amount,
                "desc": desc,
                "user": user
            })
            db["last_action"] = {"type": "spend", "amount": amount}
            save_data(db)

            bot.send_message(chat_id, f"🧾 CHI {format_money(amount)} — {desc}\n👉 Còn: {format_money(db['quy'])}")
            STATE.pop(chat_id)
            return "OK"

        # ==== NẠP QUỸ DỤNG CỤ ====
        if mode == "add_tool":
            amount = parse_amount(text)
            if amount is None:
                bot.send_message(chat_id, "⚠ Sai số tiền! Ví dụ: 50k")
                return "OK"

            db["quy_tools"] += amount
            db["lich_su_tools"].append({
                "time": now(),
                "kind": "add",
                "amount": amount,
                "desc": "Nạp quỹ dụng cụ",
                "user": user
            })
            db["last_action"] = {"type": "add_tool", "amount": amount}
            save_data(db)

            bot.send_message(chat_id, f"🛠 NẠP {format_money(amount)}\n👉 Quỹ dụng cụ: {format_money(db['quy_tools'])}")
            STATE.pop(chat_id)
            return "OK"

        # ==== CHI QUỸ DỤNG CỤ ====
        if mode == "spend_tool":
            parts = text.split(" ", 1)

            if len(parts) < 2:
                bot.send_message(chat_id, "⚠ Sai cú pháp! Ví dụ: 40k dao")
                return "OK"

            amount = parse_amount(parts[0])
            if amount is None:
                bot.send_message(chat_id, "⚠ Sai số tiền! Ví dụ: 30k")
                return "OK"

            desc = parts[1] + f" — ({user})"

            db["quy_tools"] -= amount
            db["lich_su_tools"].append({
                "time": now(),
                "kind": "spend",
                "amount": amount,
                "desc": desc,
                "user": user
            })
            db["last_action"] = {"type": "spend_tool", "amount": amount}
            save_data(db)

            bot.send_message(chat_id, f"🛠 CHI {format_money(amount)} — {desc}\n👉 Còn: {format_money(db['quy_tools'])}")
            STATE.pop(chat_id)
            return "OK"

    return "OK"


if __name__ == "__main__":
    app.run(port=5000, debug=False)
