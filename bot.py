import os
import json
import datetime
from flask import Flask, request
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

app = Flask(__name__)

TOKEN = os.getenv("BOT_TOKEN")
bot = telegram.Bot(token=TOKEN)

DATA_FILE = "data.json"

ADMIN_IDS = [977170999]      # ← Sửa theo ID admin của bạn
STATE = {}                   # Lưu trạng thái người dùng (add / spend / add_tools / spend_tools)

# ==== TIME GMT+7 ====
def now():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%d/%m/%Y %H:%M")


# ==== FORMAT TIỀN (k thay 000) ====
def format_money(amount):
    amount = int(amount)
    if amount % 1000 == 0:
        return f"{amount//1000}k"
    return f"{amount}đ"


# ==== PARSE TIỀN NGƯỜI DÙNG NHẬP ====
def parse_amount(text):
    text = text.lower().strip()

    if text.endswith("k"):
        num = text[:-1]
        if not num.isdigit():
            return None
        return int(num) * 1000

    if text.isdigit():
        return int(text)

    return None


# ==== LOAD / SAVE DATA ====
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


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# ==== MENU ====
def send_menu(chat_id):
    buttons = [
        [InlineKeyboardButton("➕ Thêm quỹ", callback_data="add_quy")],
        [InlineKeyboardButton("➖ Chi tiêu", callback_data="spend")],
        [InlineKeyboardButton("🛠 Thêm quỹ dụng cụ", callback_data="add_tool")],
        [InlineKeyboardButton("🛠 Chi dụng cụ", callback_data="spend_tool")],
        [InlineKeyboardButton("📊 Báo cáo", callback_data="report")],
        [InlineKeyboardButton("↩ Hoàn tác giao dịch cuối", callback_data="undo")],
        [InlineKeyboardButton("🧹 Xóa tin bot (admin)", callback_data="clear")]
    ]
    bot.send_message(chat_id, "📌 Chọn chức năng:", reply_markup=InlineKeyboardMarkup(buttons))


# ==== WEBHOOK ====
@app.route("/", methods=["GET"])
def home():
    return "Bot is running!"


@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = telegram.Update.de_json(request.get_json(force=True), bot)

    # === CALLBACK ===
    if update.callback_query:
        chat_id = update.callback_query.message.chat_id
        user_id = update.callback_query.from_user.id
        data = update.callback_query.data

        # RESET nhập liệu
        if data in ["add_quy", "spend", "add_tool", "spend_tool"]:
            STATE[chat_id] = data
            t = {
                "add_quy": "👉 Nhập số tiền nạp (vd: 100k hoặc 300k A nộp):",
                "spend": "👉 Nhập tiền + mô tả (vd: 50k rau, 200k thịt):",
                "add_tool": "👉 Nhập tiền nạp quỹ dụng cụ (admin):",
                "spend_tool": "👉 Nhập chi dụng cụ + mô tả (admin):"
            }
            bot.send_message(chat_id, t[data])
            return "OK"

        # XÓA TIN BOT
        if data == "clear":
            if user_id not in ADMIN_IDS:
                bot.send_message(chat_id, "⛔ Chỉ admin mới được dùng chức năng này.")
                return "OK"
            try:
                bot.delete_message(chat_id, update.callback_query.message.message_id)
            except:
                pass
            return "OK"

        # HOÀN TÁC
        if data == "undo":
            db = load_data()
            if not db["last_action"]:
                bot.send_message(chat_id, "⚠ Không có giao dịch để hoàn tác.")
                return "OK"

            act = db["last_action"]
            if act["type"] == "add":
                db["quy"] -= act["amount"]
                db["lich_su"].pop()
            if act["type"] == "spend":
                db["quy"] += act["amount"]
                db["lich_su"].pop()

            if act["type"] == "add_tool":
                db["quy_tools"] -= act["amount"]
                db["lich_su_tools"].pop()

            if act["type"] == "spend_tool":
                db["quy_tools"] += act["amount"]
                db["lich_su_tools"].pop()

            db["last_action"] = None
            save_data(db)
            bot.send_message(chat_id, "↩ Đã hoàn tác giao dịch cuối.")
            return "OK"

        # BÁO CÁO
        if data == "report":
            db = load_data()

            text = f"📊 *BÁO CÁO THÁNG {now()[3:10]}*\n\n"

            # ===== QUỸ CHÍNH =====
            text += "💰 *QUỸ CHÍNH*\n"

            total_add = sum(i["amount"] for i in db["lich_su"] if i["kind"] == "add")
            total_spend = sum(i["amount"] for i in db["lich_su"] if i["kind"] == "spend")

            text += f"• Tổng nạp: {format_money(total_add)}\n"
            for i in db["lich_su"]:
                if i["kind"] == "add":
                    text += f"  ➕ {format_money(i['amount'])} — {i['desc']} • {i['time']}\n"

            text += f"\n• Tổng chi: {format_money(total_spend)}\n"
            for i in db["lich_su"]:
                if i["kind"] == "spend":
                    text += f"  ➖ {format_money(i['amount'])} — {i['desc']} • {i['time']}\n"

            text += f"\n💵 *Quỹ chính hiện tại:* {format_money(db['quy'])}\n\n"

            # ===== QUỸ DỤNG CỤ =====
            text += "🛠 *QUỸ DỤNG CỤ*\n"

            total_add2 = sum(i["amount"] for i in db["lich_su_tools"] if i["kind"] == "add")
            total_spend2 = sum(i["amount"] for i in db["lich_su_tools"] if i["kind"] == "spend")

            text += f"• Tổng nạp: {format_money(total_add2)}\n"
            if total_add2 == 0:
                text += "  Không có\n"
            else:
                for i in db["lich_su_tools"]:
                    if i["kind"] == "add":
                        text += f"  ➕ {format_money(i['amount'])} — {i['desc']} • {i['time']}\n"

            text += f"\n• Tổng chi: {format_money(total_spend2)}\n"
            if total_spend2 == 0:
                text += "  Không có\n"
            else:
                for i in db["lich_su_tools"]:
                    if i["kind"] == "spend":
                        text += f"  ➖ {format_money(i['amount'])} — {i['desc']} • {i['time']}\n"

            text += f"\n🧰 *Quỹ dụng cụ hiện tại:* {format_money(db['quy_tools'])}"

            bot.send_message(chat_id, text, parse_mode="Markdown")
            return "OK"

    # === MESSAGE ===
    if update.message:
        chat_id = update.message.chat_id
        user = update.message.from_user.first_name
        user_id = update.message.from_user.id
        text = update.message.text.strip()

        # Trong nhóm phải có @bot
        if update.message.chat.type != "private":
            if not (update.message.text.startswith("/") or f"@{bot.username}" in update.message.text):
                return "OK"

        # Lệnh START
        if text.startswith("/start"):
            send_menu(chat_id)
            return "OK"

        # Không chọn chức năng → không ghi nhận
        if chat_id not in STATE:
            bot.send_message(chat_id, "⚠ Vui lòng chọn chức năng trước.")
            send_menu(chat_id)
            return "OK"

        mode = STATE[chat_id]
        db = load_data()

        # ===== XỬ LÝ NẠP QUỸ =====
        if mode == "add_quy":
            parts = text.split(" ", 1)
            amount_raw = parts[0]
            amount = parse_amount(amount_raw)

            if amount is None:
                bot.send_message(chat_id, "⚠ Sai định dạng! Ví dụ đúng: 100k hoặc 300k A nộp")
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

        # ===== CHI TIÊU =====
        if mode == "spend":
            parts = text.split(" ", 1)
            if len(parts) < 2:
                bot.send_message(chat_id, "⚠ Sai cấu trúc! Ví dụ: 50k rau")
                return "OK"

            amount = parse_amount(parts[0])
            if amount is None:
                bot.send_message(chat_id, "⚠ Sai số tiền! Ví dụ: 50k")
                return "OK"

            desc = parts[1]

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

            bot.send_message(chat_id, f"🧾 CHI: {format_money(amount)} — {desc}\n👉 Còn: {format_money(db['quy'])}")
            STATE.pop(chat_id)
            return "OK"

        # ===== NẠP QUỸ DỤNG CỤ (ADMIN) =====
        if mode == "add_tool":
            if user_id not in ADMIN_IDS:
                bot.send_message(chat_id, "⛔ Chỉ admin mới được dùng chức năng này.")
                return "OK"

            amount = parse_amount(text)
            if amount is None:
                bot.send_message(chat_id, "⚠ Sai số tiền! Ví dụ: 100k")
                return "OK"

            db["quy_tools"] += amount
            db["lich_su_tools"].append({
                "time": now(),
                "kind": "add",
                "amount": amount,
                "desc": f"Nạp quỹ dụng cụ",
                "user": user
            })

            db["last_action"] = {"type": "add_tool", "amount": amount}
            save_data(db)

            bot.send_message(chat_id, f"🛠 Nạp quỹ dụng cụ: {format_money(amount)}\n👉 Quỹ dụng cụ: {format_money(db['quy_tools'])}")
            STATE.pop(chat_id)
            return "OK"

        # ===== CHI DỤNG CỤ =====
        if mode == "spend_tool":
            if user_id not in ADMIN_IDS:
                bot.send_message(chat_id, "⛔ Chỉ admin mới được dùng chức năng này.")
                return "OK"

            parts = text.split(" ", 1)
            if len(parts) < 2:
                bot.send_message(chat_id, "⚠ Sai cấu trúc! Ví dụ: 30k dao")
                return "OK"

            amount = parse_amount(parts[0])
            if amount is None:
                bot.send_message(chat_id, "⚠ Sai số tiền! Ví dụ: 50k")
                return "OK"

            desc = parts[1]

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

            bot.send_message(chat_id, f"🛠 CHI dụng cụ: {format_money(amount)} — {desc}\n👉 Còn: {format_money(db['quy_tools'])}")
            STATE.pop(chat_id)
            return "OK"

    return "OK"
