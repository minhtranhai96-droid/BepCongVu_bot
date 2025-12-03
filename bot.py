import os
import json
import datetime
from flask import Flask, request
import telegram
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

# ------------- CONFIG -------------
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable not set")
bot = telegram.Bot(token=TOKEN)

# Thêm admin ở đây (số nguyên)
ADMIN_IDS = {977170999}

DATA_FILE = "data.json"

# ------------- HELPERS -------------
def now():
    """GMT+7 timestamp"""
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%d/%m/%Y %H:%M")

def format_money(amount):
    """Luôn trả về dạng k nếu phù hợp, ngược lại trả nguyên (đống tiền lẻ)"""
    amount = int(amount)
    if amount % 1000 == 0:
        return f"{amount // 1000}k"
    return f"{amount}đ"

def parse_amount(text):
    """
    Nhận '50k' -> 50000
    Nếu không đúng -> None
    """
    if not text:
        return None
    s = text.lower().strip()
    if s.endswith("k"):
        num = s[:-1]
        if num.isdigit():
            return int(num) * 1000
        return None
    # không chấp nhận chữ số thuần (theo yêu cầu bạn bắt buộc có 'k')
    return None

def ensure_db_structure(db):
    """Đảm bảo các key tồn tại"""
    if "quy" not in db:
        db["quy"] = 0
    if "quy_tools" not in db:
        db["quy_tools"] = 0
    if "lich_su" not in db:
        db["lich_su"] = []
    if "lich_su_tools" not in db:
        db["lich_su_tools"] = []
    if "modes" not in db:
        db["modes"] = {}          # lưu mode theo chat_id: db["modes"][str(chat_id)] = "add_quy" ...
    if "last_action" not in db:
        db["last_action"] = {}    # last_action theo chat_id
    return db

def load_data():
    if not os.path.exists(DATA_FILE):
        return ensure_db_structure({})
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)
    return ensure_db_structure(db)

def save_data(db):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4, ensure_ascii=False)

# ------------- UI -------------
def send_menu(chat_id):
    buttons = [
        [InlineKeyboardButton("➕ Thêm quỹ", callback_data="add_quy")],
        [InlineKeyboardButton("➖ Chi tiêu", callback_data="spend")],
        [InlineKeyboardButton("🛠 Thêm quỹ dụng cụ", callback_data="add_tool")],
        [InlineKeyboardButton("🛠 Chi dụng cụ", callback_data="spend_tool")],
        [InlineKeyboardButton("📊 Báo cáo", callback_data="report")],
        [InlineKeyboardButton("↩ Hoàn tác giao dịch cuối", callback_data="undo")],
        [InlineKeyboardButton("🧹 Xóa tin bot (admin)", callback_data="clear_bot")]
    ]
    bot.send_message(chat_id, "📌 Chọn chức năng:", reply_markup=InlineKeyboardMarkup(buttons))

# ------------- FLASK APP -------------
app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "BepCongVu bot running"

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = telegram.Update.de_json(request.get_json(force=True), bot)

    db = load_data()

    # -------- callback query (button) ----------
    if update.callback_query:
        cq = update.callback_query
        chat_id = cq.message.chat_id
        uid = cq.from_user.id
        data = cq.data

        # set mode per chat
        if data in ("add_quy", "spend", "add_tool", "spend_tool"):
            db["modes"][str(chat_id)] = data
            save_data(db)
            if data == "add_quy":
                bot.send_message(chat_id, "👉 Nhập số tiền nạp (ví dụ: 100k hoặc 300k A nộp):")
            elif data == "spend":
                bot.send_message(chat_id, "👉 Nhập số tiền + mô tả (ví dụ: 50k rau):")
            elif data == "add_tool":
                if uid not in ADMIN_IDS:
                    bot.send_message(chat_id, "⛔ Chỉ admin mới được thêm quỹ dụng cụ.")
                    return "OK"
                bot.send_message(chat_id, "👉 Nhập số tiền nạp quỹ dụng cụ (ví dụ: 200k):")
            elif data == "spend_tool":
                if uid not in ADMIN_IDS:
                    bot.send_message(chat_id, "⛔ Chỉ admin mới được chi dụng cụ.")
                    return "OK"
                bot.send_message(chat_id, "👉 Nhập số tiền + mô tả cho quỹ dụng cụ (ví dụ: 50k dao):")
            return "OK"

        # clear bot message (admin) - note: Telegram may not allow delete in group if bot not admin
        if data == "clear_bot":
            if uid not in ADMIN_IDS:
                bot.send_message(chat_id, "⛔ Chỉ admin mới dùng chức năng này.")
                return "OK"
            try:
                bot.delete_message(chat_id, cq.message.message_id)
            except Exception:
                pass
            return "OK"

        # undo last action for this chat
        if data == "undo":
            last = db["last_action"].get(str(chat_id))
            if not last:
                bot.send_message(chat_id, "⚠ Không có giao dịch để hoàn tác.")
                return "OK"
            # handle types: main_add, main_spend, tool_add, tool_spend
            t = last.get("type")
            amt = last.get("amount", 0)
            if t == "main_add":
                db["quy"] -= amt
                if db["lich_su"]:
                    db["lich_su"].pop()
            elif t == "main_spend":
                db["quy"] += amt
                if db["lich_su"]:
                    db["lich_su"].pop()
            elif t == "tool_add":
                db["quy_tools"] -= amt
                if db["lich_su_tools"]:
                    db["lich_su_tools"].pop()
            elif t == "tool_spend":
                db["quy_tools"] += amt
                if db["lich_su_tools"]:
                    db["lich_su_tools"].pop()
            db["last_action"].pop(str(chat_id), None)
            save_data(db)
            bot.send_message(chat_id, "↩ Đã hoàn tác giao dịch cuối.")
            return "OK"

        # report
        if data == "report":
            # Build report
            text = f"📊 *BÁO CÁO THÁNG {now()[3:10]}*\n\n"

            # QUỸ CHÍNH
            text += "💰 *QUỸ CHÍNH*\n"
            total_add = sum(i["amount"] for i in db["lich_su"] if i.get("kind") == "add")
            total_spend = sum(i["amount"] for i in db["lich_su"] if i.get("kind") == "spend")
            text += f"• Tổng nạp: {format_money(total_add)}\n"
            if total_add == 0:
                text += "  Không có\n"
            else:
                for item in db["lich_su"]:
                    if item.get("kind") == "add":
                        text += f"  ➕ {format_money(item['amount'])} — {item['desc']} • {item['time']}\n"
            text += f"\n• Tổng chi: {format_money(total_spend)}\n"
            if total_spend == 0:
                text += "  Không có\n"
            else:
                for item in db["lich_su"]:
                    if item.get("kind") == "spend":
                        text += f"  ➖ {format_money(item['amount'])} — {item['desc']} • {item['time']}\n"
            text += f"\n💵 *Quỹ chính hiện tại:* {format_money(db['quy'])}\n\n"

            # QUỸ DỤNG CỤ
            text += "🛠 *QUỸ DỤNG CỤ*\n"
            total_add2 = sum(i["amount"] for i in db["lich_su_tools"] if i.get("kind") == "add")
            total_spend2 = sum(i["amount"] for i in db["lich_su_tools"] if i.get("kind") == "spend")
            text += f"• Tổng nạp: {format_money(total_add2)}\n"
            if total_add2 == 0:
                text += "  Không có\n"
            else:
                for item in db["lich_su_tools"]:
                    if item.get("kind") == "add":
                        text += f"  ➕ {format_money(item['amount'])} — {item['desc']} • {item['time']}\n"
            text += f"\n• Tổng chi: {format_money(total_spend2)}\n"
            if total_spend2 == 0:
                text += "  Không có\n"
            else:
                for item in db["lich_su_tools"]:
                    if item.get("kind") == "spend":
                        text += f"  ➖ {format_money(item['amount'])} — {item['desc']} • {item['time']}\n"
            text += f"\n🧰 *Quỹ dụng cụ hiện tại:* {format_money(db['quy_tools'])}"

            bot.send_message(chat_id, text, parse_mode="Markdown")
            return "OK"

    # -------- message handling ----------
    if update.message:
        msg = update.message
        chat_id = msg.chat_id
        text = (msg.text or "").strip()
        user = msg.from_user.first_name
        uid = msg.from_user.id

        # start
        if text.startswith("/start"):
            send_menu(chat_id)
            return "OK"

        # get mode for this chat
        mode = db["modes"].get(str(chat_id))
        if not mode:
            bot.send_message(chat_id, "⚠ Vui lòng chọn chức năng trước.")
            send_menu(chat_id)
            return "OK"

        # add_quy (main fund)
        if mode == "add_quy":
            # expect "50k [ghi chu optional]"
            parts = text.split(" ", 1)
            amt = parse_amount(parts[0])
            if amt is None:
                bot.send_message(chat_id, "⚠ Sai cú pháp! Ví dụ: 100k hoặc 300k A nộp")
                return "OK"
            desc = parts[1] if len(parts) > 1 else "Nạp quỹ"
            desc = f"{desc} — ({user})"
            db["quy"] += amt
            db["lich_su"].append({"time": now(), "kind": "add", "amount": amt, "desc": desc, "user": user})
            db["last_action"][str(chat_id)] = {"type": "main_add", "amount": amt}
            db["modes"].pop(str(chat_id), None)
            save_data(db)
            bot.send_message(chat_id, f"💰 NẠP {format_money(amt)}\n👉 Quỹ: {format_money(db['quy'])}")
            send_menu(chat_id)
            return "OK"

        # spend (main)
        if mode == "spend":
            parts = text.split(" ", 1)
            if len(parts) < 2:
                bot.send_message(chat_id, "⚠ Sai cú pháp! Ví dụ: 50k rau")
                return "OK"
            amt = parse_amount(parts[0])
            if amt is None:
                bot.send_message(chat_id, "⚠ Sai số tiền! Ví dụ: 50k")
                return "OK"
            desc = f"{parts[1]} — ({user})"
            db["quy"] -= amt
            db["lich_su"].append({"time": now(), "kind": "spend", "amount": amt, "desc": desc, "user": user})
            db["last_action"][str(chat_id)] = {"type": "main_spend", "amount": amt}
            db["modes"].pop(str(chat_id), None)
            save_data(db)
            bot.send_message(chat_id, f"🧾 CHI {format_money(amt)} — {parts[1]}\n👉 Còn: {format_money(db['quy'])}")
            send_menu(chat_id)
            return "OK"

        # add_tool (admin)
        if mode == "add_tool":
            if uid not in ADMIN_IDS:
                bot.send_message(chat_id, "⛔ Chỉ admin mới được dùng chức năng này.")
                return "OK"
            amt = parse_amount(text)
            if amt is None:
                bot.send_message(chat_id, "⚠ Sai cú pháp! Ví dụ: 200k")
                return "OK"
            db["quy_tools"] += amt
            db["lich_su_tools"].append({"time": now(), "kind": "add", "amount": amt, "desc": "Nạp quỹ dụng cụ", "user": user})
            db["last_action"][str(chat_id)] = {"type": "tool_add", "amount": amt}
            db["modes"].pop(str(chat_id), None)
            save_data(db)
            bot.send_message(chat_id, f"🛠 NẠP {format_money(amt)} vào quỹ dụng cụ\n👉 Quỹ dụng cụ: {format_money(db['quy_tools'])}")
            send_menu(chat_id)
            return "OK"

        # spend_tool (admin)
        if mode == "spend_tool":
            if uid not in ADMIN_IDS:
                bot.send_message(chat_id, "⛔ Chỉ admin mới được dùng chức năng này.")
                return "OK"
            parts = text.split(" ", 1)
            if len(parts) < 2:
                bot.send_message(chat_id, "⚠ Sai cú pháp! Ví dụ: 50k dao")
                return "OK"
            amt = parse_amount(parts[0])
            if amt is None:
                bot.send_message(chat_id, "⚠ Sai số tiền! Ví dụ: 50k")
                return "OK"
            desc = f"{parts[1]} — ({user})"
            db["quy_tools"] -= amt
            db["lich_su_tools"].append({"time": now(), "kind": "spend", "amount": amt, "desc": desc, "user": user})
            db["last_action"][str(chat_id)] = {"type": "tool_spend", "amount": amt}
            db["modes"].pop(str(chat_id), None)
            save_data(db)
            bot.send_message(chat_id, f"🛠 CHI {format_money(amt)} — {parts[1]}\n👉 Quỹ dụng cụ: {format_money(db['quy_tools'])}")
            send_menu(chat_id)
            return "OK"

    return "OK"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
