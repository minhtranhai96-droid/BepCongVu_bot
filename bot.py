# bot.py
import os
import json
import datetime
from flask import Flask, request
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import pytz

# ---------- CONFIG ----------
# Admin usernames (without @). Bạn cung cấp: @tranminhhai648
ADMINS = ["tranminhhai648"]

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable required.")
bot = telegram.Bot(token=TOKEN)

# Files
DATA_FILE = "data.json"
STATE_FILE = "state.json"
MSG_FILE = "messages.json"

# Timezone
TZ = pytz.timezone("Asia/Ho_Chi_Minh")

def now_time():
    return datetime.datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

# ---------- FILE HELPERS ----------
def load_json_file(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return default

def save_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_data():
    return load_json_file(DATA_FILE, {"quy": 0, "quy_dung_cu": 0, "lich_su": []})

def save_data(d): save_json_file(DATA_FILE, d)

def load_state():
    return load_json_file(STATE_FILE, {})

def save_state(s): save_json_file(STATE_FILE, s)

def load_messages():
    return load_json_file(MSG_FILE, [])

def save_messages(m): save_json_file(MSG_FILE, m)

# ---------- MONEY FORMAT & PARSING ----------
def format_money(amount: int):
    amount = int(amount)
    if amount >= 1_000_000:
        v = amount / 1_000_000
        if v.is_integer():
            return f"{int(v)}m"
        return f"{v:.1f}m"
    if amount >= 1_000:
        return f"{amount//1000}k"
    return str(amount)

def parse_amount(token: str):
    """
    token should be like '50k', '1m' (case-insensitive).
    returns integer amount in VND (e.g. 50k -> 50000), or None if invalid.
    """
    if not token:
        return None
    t = token.lower().strip()
    if t.endswith("k") and t[:-1].isdigit():
        return int(t[:-1]) * 1000
    if t.endswith("m") and t[:-1].isdigit():
        return int(t[:-1]) * 1_000_000
    return None

# ---------- SEND & LOG ----------
def send_and_log(chat_id, text, **kwargs):
    """
    wrapper để lưu lại message_id của bot để clear sau này.
    """
    msg = bot.send_message(chat_id, text, **kwargs)
    msgs = load_messages()
    msgs.append({"chat_id": chat_id, "msg_id": msg.message_id})
    save_messages(msgs)
    return msg

# ---------- ADMIN CHECK ----------
def is_username_admin(username: str):
    if not username:
        return False
    u = username.lstrip("@").lower()
    return u in [a.lower() for a in ADMINS]

def is_chat_admin(chat_id, user_id):
    """
    Kiểm tra admin trực tiếp từ Telegram (dùng cho nhóm).
    Falls back to username list if Telegram check fails.
    """
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False

# ---------- MENU ----------
def send_menu(chat_id, sender_username=None, sender_id=None):
    """
    Nếu sender_username hoặc sender_id là admin -> show admin buttons.
    caller should pass either username (for private chats) or id when available.
    """
    is_admin_user = False
    if sender_username and is_username_admin(sender_username):
        is_admin_user = True
    elif sender_id is not None:
        try:
            # try group-based admin check (works if bot in group)
            is_admin_user = is_chat_admin(chat_id, sender_id)
        except:
            pass

    buttons = [
        [InlineKeyboardButton("➕ Thêm quỹ", callback_data="add_quy")],
        [InlineKeyboardButton("➖ Chi tiêu", callback_data="chi_tieu")]
    ]

    # Admin-only quỹ dụng cụ buttons
    if is_admin_user:
        buttons.append([InlineKeyboardButton("🛠️ Thêm quỹ dụng cụ", callback_data="add_dc")])
        buttons.append([InlineKeyboardButton("🛠️ Chi dụng cụ", callback_data="spend_dc")])

    buttons.append([InlineKeyboardButton("📊 Báo cáo", callback_data="report_all")])
    buttons.append([InlineKeyboardButton("↩ Hoàn tác giao dịch cuối", callback_data="undo")])
    buttons.append([InlineKeyboardButton("🧹 Xóa tin bot (admin)", callback_data="clear_msgs")])

    send_and_log(chat_id, "📌 Chọn chức năng:", reply_markup=InlineKeyboardMarkup(buttons))

# ---------- FLASK & WEBHOOK ----------
app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    return "Bot is running."

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = telegram.Update.de_json(request.get_json(force=True), bot)

    # CALLBACK queries (button presses)
    if update.callback_query:
        cq = update.callback_query
        chat_id = cq.message.chat.id
        user = cq.from_user
        username = user.username or ""
        user_id = user.id
        action = cq.data

        # save state (so that next text message is understood)
        state = load_state()
        state[str(chat_id)] = action
        save_state(state)

        data = load_data()

        # ---- UNDO (button) ----
        if action == "undo":
            if not data["lich_su"]:
                send_and_log(chat_id, "⚠️ Không có giao dịch nào để hoàn tác.")
                return "OK"
            last = data["lich_su"][-1]
            # user identity: prefer username if available, else use first_name
            last_user = last.get("user_username") or last.get("user_name")
            # current user identity
            cur_user = username or user.first_name
            if last_user and (last_user.lstrip("@").lower() != cur_user.lstrip("@").lower()):
                send_and_log(chat_id, "⛔ Bạn không thể hoàn tác giao dịch của người khác.")
                return "OK"
            removed = data["lich_su"].pop()
            if removed["type"] in ("add",):
                data["quy"] -= removed["amount"]
            elif removed["type"] in ("spend",):
                data["quy"] += removed["amount"]
            elif removed["type"] == "add_dc":
                data["quy_dung_cu"] -= removed["amount"]
            elif removed["type"] == "spend_dc":
                data["quy_dung_cu"] += removed["amount"]
            save_data(data)
            send_and_log(chat_id, f"🗑 HOÀN TÁC: {format_money(removed['amount'])} — {removed['desc']}\n💵 Quỹ chính: {format_money(data['quy'])}\n🛠 Quỹ dụng cụ: {format_money(data.get('quy_dung_cu',0))}")
            send_menu(chat_id, sender_username=username, sender_id=user_id)
            return "OK"

        # ---- CLEAR MESSAGES (admin only, in groups) ----
        if action == "clear_msgs":
            # check either username admin or chat admin
            allowed = False
            if is_username_admin(username):
                allowed = True
            else:
                try:
                    chat = bot.get_chat(chat_id)
                    if chat.type in ("group", "supergroup"):
                        member = bot.get_chat_member(chat_id, user_id)
                        if member.status in ("administrator", "creator"):
                            allowed = True
                    else:
                        # private chat -> allow only if username in ADMINS
                        allowed = is_username_admin(username)
                except Exception:
                    allowed = False

            if not allowed:
                send_and_log(chat_id, "⛔ Chỉ quản trị viên mới được dùng chức năng này.")
                return "OK"

            msgs = load_messages()
            deleted = 0
            for m in msgs:
                try:
                    bot.delete_message(m["chat_id"], m["msg_id"])
                    deleted += 1
                except:
                    pass
            save_messages([])
            send_and_log(chat_id, f"🧹 Đã xoá {deleted} tin nhắn bot. (Lịch sử quỹ không thay đổi)")
            send_menu(chat_id, sender_username=username, sender_id=user_id)
            return "OK"

        # ---- QUỸ DỤNG CỤ (admin only) ----
        if action == "add_dc":
            if not (is_username_admin(username) or is_chat_admin(cq.message.chat.id, user_id)):
                send_and_log(chat_id, "⛔ Chỉ admin mới được dùng chức năng này.")
                return "OK"
            send_and_log(chat_id, "👉 Nhập tiền nạp cho *Quỹ dụng cụ* (vd: 300k hoặc 1m):", parse_mode="Markdown")
            return "OK"

        if action == "spend_dc":
            if not (is_username_admin(username) or is_chat_admin(cq.message.chat.id, user_id)):
                send_and_log(chat_id, "⛔ Chỉ admin mới được dùng chức năng này.")
                return "OK"
            send_and_log(chat_id, "👉 Nhập chi tiêu cho *Quỹ dụng cụ* (vd: 200k dao):", parse_mode="Markdown")
            return "OK"

        # ---- NORMAL: add_quy, chi_tieu, report_all ----
        if action == "add_quy":
            send_and_log(chat_id, "👉 Nhập tiền nạp cho *Quỹ chính* (vd: 100k hoặc 300k A nộp):", parse_mode="Markdown")
            return "OK"

        if action == "chi_tieu":
            send_and_log(chat_id, "👉 Nhập chi tiêu cho *Quỹ chính* (vd: 50k rau, 200k thịt):", parse_mode="Markdown")
            return "OK"

        if action == "report_all":
            # prepare report with two separate sections
            now = datetime.datetime.now(TZ)
            month = now.strftime("%m")
            year = now.strftime("%Y")
            data = load_data()

            records_month = [r for r in data["lich_su"] if r["time"][5:7] == month and r["time"][0:4] == year]

            add_main = [r for r in records_month if r["type"] == "add"]
            spend_main = [r for r in records_month if r["type"] == "spend"]
            add_dc = [r for r in records_month if r["type"] == "add_dc"]
            spend_dc = [r for r in records_month if r["type"] == "spend_dc"]

            total_add_main = sum(i["amount"] for i in add_main)
            total_spend_main = sum(i["amount"] for i in spend_main)
            total_add_dc = sum(i["amount"] for i in add_dc)
            total_spend_dc = sum(i["amount"] for i in spend_dc)

            msg = f"📊 *BÁO CÁO THÁNG {month}/{year}*\n\n"
            # Main fund
            msg += f"💰 *QUỸ CHÍNH*\n"
            msg += f"• Tổng nạp: {format_money(total_add_main)}\n"
            if add_main:
                for i in add_main:
                    t = datetime.datetime.strptime(i["time"], "%Y-%m-%d %H:%M:%S").strftime("%d/%m %H:%M")
                    msg += f"   ➕ {format_money(i['amount'])} — {i['desc']} • {t}\n"
            else:
                msg += "   Không có\n"

            msg += f"\n• Tổng chi: {format_money(total_spend_main)}\n"
            if spend_main:
                for i in spend_main:
                    t = datetime.datetime.strptime(i["time"], "%Y-%m-%d %H:%M:%S").strftime("%d/%m %H:%M")
                    msg += f"   ➖ {format_money(i['amount'])} — {i['desc']} • {t}\n"
            else:
                msg += "   Không có\n"

            msg += f"\n💵 Quỹ chính hiện tại: {format_money(data.get('quy',0))}\n\n"

            # Tool fund
            msg += f"🛠 *QUỸ DỤNG CỤ*\n"
            msg += f"• Tổng nạp: {format_money(total_add_dc)}\n"
            if add_dc:
                for i in add_dc:
                    t = datetime.datetime.strptime(i["time"], "%Y-%m-%d %H:%M:%S").strftime("%d/%m %H:%M")
                    msg += f"   ➕ {format_money(i['amount'])} — {i['desc']} • {t}\n"
            else:
                msg += "   Không có\n"

            msg += f"\n• Tổng chi: {format_money(total_spend_dc)}\n"
            if spend_dc:
                for i in spend_dc:
                    t = datetime.datetime.strptime(i["time"], "%Y-%m-%d %H:%M:%S").strftime("%d/%m %H:%M")
                    msg += f"   ➖ {format_money(i['amount'])} — {i['desc']} • {t}\n"
            else:
                msg += "   Không có\n"

            msg += f"\n🧾 Quỹ dụng cụ hiện tại: {format_money(data.get('quy_dung_cu',0))}"

            send_and_log(chat_id, msg, parse_mode="Markdown")
            return "OK"

        return "OK"

    # MESSAGE (text) handling
    if update.message:
        msg = update.message
        chat_id = msg.chat.id
        user = msg.from_user
        username = user.username or ""
        user_id = user.id
        text = (msg.text or "").strip()

        # commands
        if text.startswith("/start"):
            send_menu(chat_id, sender_username=username, sender_id=user_id)
            return "OK"

        # /undo text command (allow)
        if text.lower().strip() == "/undo":
            # emulate button undo
            state = load_state()
            # don't change state, just perform undo
            data = load_data()
            if not data["lich_su"]:
                send_and_log(chat_id, "⚠️ Không có giao dịch nào để hoàn tác.")
                return "OK"
            last = data["lich_su"][-1]
            last_user = last.get("user_username") or last.get("user_name")
            cur_user = username or user.first_name
            if last_user and (last_user.lstrip("@").lower() != cur_user.lstrip("@").lower()):
                send_and_log(chat_id, "⛔ Bạn không thể hoàn tác giao dịch của người khác.")
                return "OK"
            removed = data["lich_su"].pop()
            if removed["type"] == "add":
                data["quy"] -= removed["amount"]
            elif removed["type"] == "spend":
                data["quy"] += removed["amount"]
            elif removed["type"] == "add_dc":
                data["quy_dung_cu"] -= removed["amount"]
            elif removed["type"] == "spend_dc":
                data["quy_dung_cu"] += removed["amount"]
            save_data(data)
            send_and_log(chat_id, f"🗑 HOÀN TÁC: {format_money(removed['amount'])} — {removed['desc']}\n💵 Quỹ chính: {format_money(data['quy'])}\n🛠 Quỹ dụng cụ: {format_money(data.get('quy_dung_cu',0))}")
            send_menu(chat_id, sender_username=username, sender_id=user_id)
            return "OK"

        # /clear command (text) route -> only admin
        if text.lower().strip() == "/clear":
            allowed = False
            if is_username_admin(username):
                allowed = True
            else:
                try:
                    chat = bot.get_chat(chat_id)
                    if chat.type in ("group", "supergroup"):
                        member = bot.get_chat_member(chat_id, user_id)
                        if member.status in ("administrator", "creator"):
                            allowed = True
                except:
                    allowed = False
            if not allowed:
                send_and_log(chat_id, "⛔ Bạn không có quyền dùng lệnh này.")
                return "OK"
            msgs = load_messages()
            deleted = 0
            for m in msgs:
                try:
                    bot.delete_message(m["chat_id"], m["msg_id"])
                    deleted += 1
                except:
                    pass
            save_messages([])
            send_and_log(chat_id, f"🧹 Đã xoá {deleted} tin nhắn bot. (Lịch sử quỹ không bị ảnh hưởng)")
            send_menu(chat_id, sender_username=username, sender_id=user_id)
            return "OK"

        # Otherwise handle based on state saved for this chat
        state = load_state()
        mode = state.get(str(chat_id))

        # if no active mode ask to pick
        if not mode or mode not in ("add_quy","chi_tieu","add_dc","spend_dc"):
            send_and_log(chat_id, "⚠️ Vui lòng chọn chức năng trước.")
            send_menu(chat_id, sender_username=username, sender_id=user_id)
            return "OK"

        data = load_data()

        # ---------- ADD MAIN FUND ----------
        if mode == "add_quy":
            # require first token valid like 50k / 1m
            token = text.split(" ",1)[0].lower()
            amount = parse_amount(token)
            if amount is None:
                send_and_log(chat_id, "❌ Sai cú pháp! Ví dụ: 50k hoặc 1m\n👉 Nhập lại:")
                return "OK"
            desc = text[len(token):].strip() or "Nạp quỹ"
            # store both username and display name
            entry = {
                "time": now_time(),
                "type": "add",
                "amount": amount,
                "desc": desc,
                "user_name": user.first_name,
                "user_username": ("@" + username) if username else ""
            }
            data["quy"] = data.get("quy",0) + amount
            data["lich_su"].append(entry)
            save_data(data)
            send_and_log(chat_id, f"💰 NẠP {format_money(amount)}\n🧾 {desc} — ({user.first_name})\n👉 Quỹ: {format_money(data['quy'])}")
            state[str(chat_id)] = None
            save_state(state)
            send_menu(chat_id, sender_username=username, sender_id=user_id)
            return "OK"

        # ---------- SPEND MAIN FUND ----------
        if mode == "chi_tieu":
            items = [i.strip() for i in text.split(",") if i.strip()]
            if not items:
                send_and_log(chat_id, "❌ Sai cú pháp! Ví dụ: 50k rau\n👉 Nhập lại:")
                return "OK"
            records = []
            total = 0
            for it in items:
                parts = it.split(" ",1)
                token = parts[0].lower()
                amount = parse_amount(token)
                if amount is None:
                    send_and_log(chat_id, "❌ Sai cú pháp ở một khoản! Ví dụ: 50k rau, 200k thịt\n👉 Nhập lại toàn bộ:")
                    return "OK"
                desc = parts[1].strip() if len(parts)>1 else "Chi tiêu"
                entry = {"time": now_time(), "type":"spend", "amount": amount, "desc": desc, "user_name": user.first_name, "user_username": ("@" + username) if username else ""}
                records.append(entry)
                total += amount
            for r in records:
                data["lich_su"].append(r)
            data["quy"] = data.get("quy",0) - total
            save_data(data)
            # backup & reset if zero
            if data.get("quy",0) == 0:
                now = datetime.datetime.now(TZ)
                backup_file = f"backup_{now.strftime('%Y%m%d_%H%M%S')}.json"
                save_json_file(backup_file, data)
                data["lich_su"] = []
                save_data(data)
                send_and_log(chat_id, f"🧾 CHI {format_money(total)} thành công.\n💵 Quỹ hiện tại: 0\n📦 Tự động backup và reset chu kỳ.")
                state[str(chat_id)] = None
                save_state(state)
                send_menu(chat_id, sender_username=username, sender_id=user_id)
                return "OK"
            send_and_log(chat_id, f"🧾 CHI {format_money(total)} thành công!\n👉 Quỹ còn: {format_money(data['quy'])}")
            state[str(chat_id)] = None
            save_state(state)
            send_menu(chat_id, sender_username=username, sender_id=user_id)
            return "OK"

        # ---------- ADD TOOL FUND (admin only) ----------
        if mode == "add_dc":
            # permit only admins
            if not (is_username_admin(username) or is_chat_admin(chat_id, user_id)):
                send_and_log(chat_id, "⛔ Bạn không có quyền nạp quỹ dụng cụ.")
                return "OK"
            token = text.split(" ",1)[0].lower()
            amount = parse_amount(token)
            if amount is None:
                send_and_log(chat_id, "❌ Sai cú pháp! Ví dụ: 300k\n👉 Nhập lại:")
                return "OK"
            desc = text[len(token):].strip() or "Nạp quỹ dụng cụ"
            entry = {"time": now_time(), "type":"add_dc", "amount": amount, "desc": desc, "user_name": user.first_name, "user_username": ("@" + username) if username else ""}
            data["quy_dung_cu"] = data.get("quy_dung_cu",0) + amount
            data["lich_su"].append(entry)
            save_data(data)
            send_and_log(chat_id, f"🛠️ NẠP {format_money(amount)} vào quỹ dụng cụ.\n👉 Quỹ dụng cụ: {format_money(data['quy_dung_cu'])}")
            state[str(chat_id)] = None
            save_state(state)
            send_menu(chat_id, sender_username=username, sender_id=user_id)
            return "OK"

        # ---------- SPEND TOOL FUND (admin only) ----------
        if mode == "spend_dc":
            if not (is_username_admin(username) or is_chat_admin(chat_id, user_id)):
                send_and_log(chat_id, "⛔ Bạn không có quyền chi từ quỹ dụng cụ.")
                return "OK"
            parts = text.split(" ",1)
            token = parts[0].lower()
            amount = parse_amount(token)
            if amount is None:
                send_and_log(chat_id, "❌ Sai cú pháp! Ví dụ: 200k dao\n👉 Nhập lại:")
                return "OK"
            desc = parts[1].strip() if len(parts)>1 else "Chi dụng cụ"
            entry = {"time": now_time(), "type":"spend_dc", "amount": amount, "desc": desc, "user_name": user.first_name, "user_username": ("@" + username) if username else ""}
            data["quy_dung_cu"] = data.get("quy_dung_cu",0) - amount
            data["lich_su"].append(entry)
            save_data(data)
            send_and_log(chat_id, f"🛠️ CHI {format_money(amount)} — {desc}\n👉 Quỹ dụng cụ còn: {format_money(data['quy_dung_cu'])}")
            state[str(chat_id)] = None
            save_state(state)
            send_menu(chat_id, sender_username=username, sender_id=user_id)
            return "OK"

        # fallback
        send_and_log(chat_id, "⚠️ Lệnh không nhận diện được. Vui lòng chọn chức năng từ menu.")
        send_menu(chat_id, sender_username=username, sender_id=user_id)
        return "OK"

    return "OK"

if __name__ == "__main__":
    # Run on port from env or default 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
