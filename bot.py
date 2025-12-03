import os
import json
import datetime
from flask import Flask, request
import telegram
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("BOT_TOKEN")
bot = telegram.Bot(TOKEN)

ADMIN_IDS = {  # chỉ admin được dùng tính năng đặc biệt
    123456789,   # thêm ID thật của bạn
    987654321
}

DATA_FILE = "data.json"

# =========================
# FORMAT TIỀN (CHỈ DÙNG k)
# =========================
def format_money(amount):
    amount = int(amount)
    return f"{amount // 1000}k"

# =========================
# LOAD – SAVE DATA
# =========================
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


# =========================
# GET TIME GMT+7
# =========================
def now():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%d/%m/%Y %H:%M")


# =========================
# MENU CHÍNH
# =========================
def send_menu(chat_id):
    buttons = [
        [InlineKeyboardButton("➕ Thêm quỹ", callback_data="add_main")],
        [InlineKeyboardButton("➖ Chi tiêu", callback_data="spend_main")],
        [InlineKeyboardButton("🛠 Thêm quỹ dụng cụ", callback_data="add_tool")],
        [InlineKeyboardButton("🛠 Chi dụng cụ", callback_data="spend_tool")],
        [InlineKeyboardButton("📊 Báo cáo", callback_data="report")],
        [InlineKeyboardButton("↩ Hoàn tác giao dịch cuối", callback_data="undo")],
        [InlineKeyboardButton("🧹 Xóa tin bot (admin)", callback_data="clear_bot")]
    ]
    bot.send_message(chat_id, "📌 Chọn chức năng:", reply_markup=InlineKeyboardMarkup(buttons))


# =========================
# VALIDATION SỐ TIỀN
# =========================
def parse_amount(txt):
    txt = txt.lower().strip()
    if not txt.endswith("k"):
        return None
    number = txt[:-1]

    if not number.isdigit():
        return None
    return int(number) * 1000


# =========================
# WEBHOOK
# =========================
app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "Bot is running!"


@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = telegram.Update.de_json(request.get_json(), bot)

    # =========================
    # XỬ LÝ NÚT BẤM
    # =========================
    if update.callback_query:
        chat_id = update.callback_query.message.chat_id
        uid = update.callback_query.from_user.id
        user = update.callback_query.from_user.first_name
        data = update.callback_query.data
        db = load_data()

        # -------------------------
        # CLEAR BOT (ADMIN ONLY)
        # -------------------------
        if data == "clear_bot":
            if uid not in ADMIN_IDS:
                bot.send_message(chat_id, "⛔ Chỉ quản trị viên mới dùng chức năng này.")
                return "OK"
            bot.send_message(chat_id, "🧹 Tin nhắn bot sẽ được xóa tự động trong nhóm (khi bạn tự xóa).")
            return "OK"

        # -------------------------
        # THÊM QUỸ
        # -------------------------
        if data == "add_main":
            db["mode"] = "add_main"
            save_data(db)
            bot.send_message(chat_id, "👉 Nhập tiền nạp (vd: 100k hoặc 300k A nộp):")
            return "OK"

        # -------------------------
        # CHI TIÊU
        # -------------------------
        if data == "spend_main":
            db["mode"] = "spend_main"
            save_data(db)
            bot.send_message(chat_id, "👉 Nhập số tiền + mô tả (vd: 50k rau, 200k gas):")
            return "OK"

        # -------------------------
        # ADD TOOL FUND (ADMIN)
        # -------------------------
        if data == "add_tool":
            if uid not in ADMIN_IDS:
                bot.send_message(chat_id, "⛔ Chỉ admin mới được thêm quỹ dụng cụ.")
                return "OK"
            db["mode"] = "add_tool"
            save_data(db)
            bot.send_message(chat_id, "👉 Nhập tiền nạp quỹ dụng cụ (vd: 200k):")
            return "OK"

        # -------------------------
        # SPEND TOOL FUND (ADMIN)
        # -------------------------
        if data == "spend_tool":
            if uid not in ADMIN_IDS:
                bot.send_message(chat_id, "⛔ Chỉ admin mới được chi quỹ dụng cụ.")
                return "OK"
            db["mode"] = "spend_tool"
            save_data(db)
            bot.send_message(chat_id, "👉 Nhập số tiền + mô tả (vd: 50k kéo, 100k dao):")
            return "OK"

        # -------------------------
        # UNDO
        # -------------------------
        if data == "undo":
            if not db.get("last_action"):
                bot.send_message(chat_id, "⚠ Không có giao dịch để hoàn tác.")
                return "OK"

            action = db["last_action"]

            # Hoàn tác nạp/chi chính
            if action["type"] == "main_add":
                db["quy"] -= action["amount"]
                db["lich_su"].pop()

            elif action["type"] == "main_spend":
                db["quy"] += action["amount"]
                db["lich_su"].pop()

            # Hoàn tác dụng cụ
            elif action["type"] == "tool_add":
                db["quy_tools"] -= action["amount"]
                db["lich_su_tools"].pop()

            elif action["type"] == "tool_spend":
                db["quy_tools"] += action["amount"]
                db["lich_su_tools"].pop()

            db["last_action"] = None
            save_data(db)

            bot.send_message(chat_id, "↩ Đã hoàn tác giao dịch cuối.")
            return "OK"

        # -------------------------
        # REPORT
        # -------------------------
        if data == "report":
            db = load_data()

            msg = f"📊 **BÁO CÁO THÁNG {now()[3:10]}**\n\n"

            # QUỸ CHÍNH
            msg += "💰 **QUỸ CHÍNH**\n"
            total_add = sum(i["amount"] for i in db["lich_su"] if i["kind"] == "add")
            msg += f"• Tổng nạp: {format_money(total_add)}\n"
            for item in db["lich_su"]:
                sign = "+" if item["kind"] == "add" else "−"
                msg += f"{sign} {format_money(item['amount'])} — {item['desc']} — ({item['user']}) • {item['time']}\n"
            msg += f"\n👉 Quỹ hiện tại: {format_money(db['quy'])}\n\n"

            # QUỸ DỤNG CỤ
            msg += "🛠 **QUỸ DỤNG CỤ**\n"
            total_add2 = sum(i["amount"] for i in db["lich_su_tools"] if i["kind"] == "add")
            msg += f"• Tổng nạp: {format_money(total_add2)}\n"
            for item in db["lich_su_tools"]:
                sign = "+" if item["kind"] == "add" else "−"
                msg += f"{sign} {format_money(item['amount'])} — {item['desc']} — ({item['user']}) • {item['time']}\n"
            msg += f"\n👉 Quỹ dụng cụ: {format_money(db['quy_tools'])}"

            bot.send_message(chat_id, msg, parse_mode="Markdown")
            return "OK"

    # ===========================================
    # XỬ LÝ NHẬP TIN NHẮN
    # ===========================================
    if update.message:
        chat_id = update.message.chat_id
        uid = update.message.from_user.id
        user = update.message.from_user.first_name
        txt = update.message.text.strip()
        db = load_data()

        # Start
        if txt.startswith("/start"):
            send_menu(chat_id)
            return "OK"

        mode = db.get("mode")
        if not mode:
            bot.send_message(chat_id, "⚠ Vui lòng chọn chức năng trước:")
            send_menu(chat_id)
            return "OK"

        # =========================
        # NẠP QUỸ CHÍNH
        # =========================
        if mode == "add_main":
            parts = txt.split(" ", 1)
            amount = parse_amount(parts[0])
            if not amount:
                bot.send_message(chat_id, "⚠ Sai cấu trúc! Ví dụ: 100k hoặc 300k A nộp")
                return "OK"

            desc = parts[1] if len(parts) > 1 else f"Nạp quỹ"
            desc += f" — ({user})"

            db["quy"] += amount
            db["lich_su"].append({
                "kind": "add",
                "amount": amount,
                "desc": desc,
                "user": user,
                "time": now()
            })
            db["last_action"] = {"type": "main_add", "amount": amount}
            db["mode"] = None
            save_data(db)

            bot.send_message(chat_id, f"💰 NẠP {format_money(amount)}\n👉 Quỹ: {format_money(db['quy'])}")
            send_menu(chat_id)
            return "OK"

        # =========================
        # CHI QUỸ CHÍNH
        # =========================
        if mode == "spend_main":
            parts = txt.split(" ", 1)
            amount = parse_amount(parts[0])
            if not amount or len(parts) < 2:
                bot.send_message(chat_id, "⚠ Sai cấu trúc! Ví dụ: 50k rau")
                return "OK"

            desc = parts[1] + f" — ({user})"

            db["quy"] -= amount
            db["lich_su"].append({
                "kind": "spend",
                "amount": amount,
                "desc": desc,
                "user": user,
                "time": now()
            })
            db["last_action"] = {"type": "main_spend", "amount": amount}
            db["mode"] = None
            save_data(db)

            bot.send_message(chat_id, f"🧾 CHI: {format_money(amount)} — {parts[1]}\n👉 Còn: {format_money(db['quy'])}")
            send_menu(chat_id)
            return "OK"

        # =========================
        # ADD TOOL FUND
        # =========================
        if mode == "add_tool":
            if uid not in ADMIN_IDS:
                bot.send_message(chat_id, "⛔ Chỉ admin dùng chức năng này.")
                return "OK"

            amount = parse_amount(txt)
            if not amount:
                bot.send_message(chat_id, "⚠ Sai cấu trúc! Ví dụ: 200k")
                return "OK"

            db["quy_tools"] += amount
            db["lich_su_tools"].append({
                "kind": "add",
                "amount": amount,
                "desc": "Nạp quỹ dụng cụ",
                "user": user,
                "time": now()
            })
            db["last_action"] = {"type": "tool_add", "amount": amount}
            db["mode"] = None
            save_data(db)

            bot.send_message(chat_id, f"🛠 NẠP {format_money(amount)}\n👉 Quỹ dụng cụ: {format_money(db['quy_tools'])}")
            send_menu(chat_id)
            return "OK"

        # =========================
        # SPEND TOOL FUND
        # =========================
        if mode == "spend_tool":
            if uid not in ADMIN_IDS:
                bot.send_message(chat_id, "⛔ Chỉ admin dùng chức năng này.")
                return "OK"

            parts = txt.split(" ", 1)
            amount = parse_amount(parts[0])
            if not amount or len(parts) < 2:
                bot.send_message(chat_id, "⚠ Sai cấu trúc! Ví dụ: 50k kéo")
                return "OK"

            desc = parts[1] + f" — ({user})"

            db["quy_tools"] -= amount
            db["lich_su_tools"].append({
                "kind": "spend",
                "amount": amount,
                "desc": desc,
                "user": user,
                "time": now()
            })
            db["last_action"] = {"type": "tool_spend", "amount": amount}
            db["mode"] = None
            save_data(db)

            bot.send_message(chat_id, f"🛠 CHI: {format_money(amount)} — {parts[1]}\n👉 Quỹ dụng cụ: {format_money(db['quy_tools'])}")
            send_menu(chat_id)
            return "OK"

    return "OK"
