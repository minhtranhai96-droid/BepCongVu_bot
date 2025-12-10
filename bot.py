import os
import datetime
from flask import Flask, request
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ========== CẤU HÌNH CƠ BẢN ==========

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Thiếu BOT_TOKEN trong Environment variables trên Render")

bot = telegram.Bot(token=TOKEN)

# Google Sheet ID – dùng env nếu có, không thì dùng luôn ID bạn gửi
SHEET_ID = os.getenv(
    "GOOGLE_SHEET_ID",
    "1VUbS7HzNHm7k3kwgIDLkNwKg7crRmSY7Rl_18taTSDk"
)

# Tên file key – sẽ được tạo tự động từ biến SERVICE_JSON
SERVICE_JSON_FILE = "service.json"

# Admin (quỹ dụng cụ chỉ admin dùng)
ADMIN_IDS = {977170999}  # sửa/nhân bản thêm nếu cần


# ========== TẠO FILE service.json TỪ ENV ==========
service_json_env = os.getenv("SERVICE_JSON")
if service_json_env:
    # Nếu file chưa tồn tại hoặc nội dung khác thì ghi lại
    need_write = True
    if os.path.exists(SERVICE_JSON_FILE):
        try:
            with open(SERVICE_JSON_FILE, "r", encoding="utf-8") as f:
                current = f.read()
            if current.strip() == service_json_env.strip():
                need_write = False
        except Exception:
            need_write = True

    if need_write:
        with open(SERVICE_JSON_FILE, "w", encoding="utf-8") as f:
            f.write(service_json_env)
else:
    raise RuntimeError("Thiếu SERVICE_JSON trong Environment variables trên Render")

# ========== KẾT NỐI GOOGLE SHEETS ==========

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

creds = Credentials.from_service_account_file(SERVICE_JSON_FILE, scopes=SCOPES)
sheets_service = build("sheets", "v4", credentials=creds).spreadsheets()

# 2 sheet: quỹ chính & quỹ dụng cụ
RANGE_MAIN = "QuyChinh!A:E"
RANGE_TOOLS = "QuyDungCu!A:E"


# ========== HÀM TIỆN ÍCH ==========

def now():
    """Thời gian GMT+7, format dd/mm/YYYY HH:MM"""
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%d/%m/%Y %H:%M")


def format_money(amount: int) -> str:
    """Định dạng tiền: 1526000 -> '1526k'."""
    return f"{int(amount) // 1000}k"


def parse_amount(token: str):
    """
    Nhận token kiểu '50k' -> trả về 50000.
    Nếu sai cấu trúc (không có 'k' hoặc phần số không phải digit) -> None.
    """
    s = token.lower().strip()
    if s.endswith("k") and s[:-1].isdigit():
        return int(s[:-1]) * 1000
    return None


def read_sheet(sheet_range):
    """Đọc toàn bộ values của range (list[list[str]])"""
    res = sheets_service.values().get(
        spreadsheetId=SHEET_ID,
        range=sheet_range
    ).execute()
    return res.get("values", [])


def write_sheet(sheet_range, values):
    """Ghi đè toàn bộ range bằng values mới."""
    sheets_service.values().clear(
        spreadsheetId=SHEET_ID,
        range=sheet_range
    ).execute()
    if values:
        sheets_service.values().update(
            spreadsheetId=SHEET_ID,
            range=sheet_range,
            valueInputOption="RAW",
            body={"values": values}
        ).execute()


def append_row(sheet_range, row):
    """Thêm 1 dòng cuối vào sheet."""
    sheets_service.values().append(
        spreadsheetId=SHEET_ID,
        range=sheet_range,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]}
    ).execute()


def calc_totals(rows):
    """
    Tính tổng nạp, tổng chi, số dư từ list row:
    row = [time, kind, amount, desc, user]
    """
    total_add = 0
    total_spend = 0
    for r in rows:
        if len(r) < 3:
            continue
        kind = r[1]
        try:
            amount = int(r[2])
        except ValueError:
            continue
        if kind == "add":
            total_add += amount
        elif kind == "spend":
            total_spend += amount
    balance = total_add - total_spend
    return total_add, total_spend, balance


# ========== TRẠNG THÁI BOT ==========

# STATE[chat_id] = 'add_main' | 'spend_main' | 'add_tool' | 'spend_tool'
STATE = {}

# UNDO_DATA[chat_id] = {'fund': 'main'|'tool'}
UNDO_DATA = {}


def send_menu(chat_id):
    """Gửi menu chính."""
    buttons = [
        [InlineKeyboardButton("➕ Thêm quỹ", callback_data="add_main")],
        [InlineKeyboardButton("➖ Chi tiêu", callback_data="spend_main")],
        [InlineKeyboardButton("🛠 Thêm quỹ dụng cụ", callback_data="add_tool")],
        [InlineKeyboardButton("🛠 Chi dụng cụ", callback_data="spend_tool")],
        [InlineKeyboardButton("📊 Báo cáo", callback_data="report")],
        [InlineKeyboardButton("↩ Hoàn tác giao dịch cuối", callback_data="undo")],
    ]
    bot.send_message(
        chat_id,
        "📌 Chọn chức năng:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ========== FLASK APP ==========

app = Flask(__name__)


@app.route("/", methods=["GET"])
def home():
    return "BepCongVu Bot using Google Sheets is running."


@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = telegram.Update.de_json(request.get_json(force=True), bot)

    # ===== CALLBACK QUERY (bấm nút) =====
    if update.callback_query:
        cq = update.callback_query
        chat_id = cq.message.chat_id
        uid = cq.from_user.id
        data = cq.data

        if data in {"add_main", "spend_main", "add_tool", "spend_tool"}:
            STATE[chat_id] = data

        if data == "add_main":
            bot.send_message(chat_id, "👉 Nhập số tiền nạp (vd: `100k` hoặc `300k A nộp`):", parse_mode="Markdown")
            return "OK"

        if data == "spend_main":
            bot.send_message(chat_id, "👉 Nhập số tiền + mô tả (vd: `50k rau`):", parse_mode="Markdown")
            return "OK"

        if data == "add_tool":
            if uid not in ADMIN_IDS:
                bot.send_message(chat_id, "⛔ Chỉ quản trị viên mới thêm quỹ dụng cụ.")
                return "OK"
            bot.send_message(chat_id, "👉 Nhập số tiền nạp quỹ dụng cụ (vd: `200k dao, thớt`):", parse_mode="Markdown")
            return "OK"

        if data == "spend_tool":
            if uid not in ADMIN_IDS:
                bot.send_message(chat_id, "⛔ Chỉ quản trị viên mới chi quỹ dụng cụ.")
                return "OK"
            bot.send_message(chat_id, "👉 Nhập số tiền + mô tả dụng cụ (vd: `150k nồi`):", parse_mode="Markdown")
            return "OK"

        if data == "undo":
            # Hoàn tác giao dịch cuối
            info = UNDO_DATA.get(chat_id)
            if not info:
                bot.send_message(chat_id, "⚠ Không có giao dịch nào để hoàn tác.")
                return "OK"

            fund = info["fund"]
            rng = RANGE_MAIN if fund == "main" else RANGE_TOOLS
            rows = read_sheet(rng)
            if not rows:
                bot.send_message(chat_id, "⚠ Sheet trống, không thể hoàn tác.")
                return "OK"

            # Xoá dòng cuối
            rows = rows[:-1]
            write_sheet(rng, rows)
            UNDO_DATA.pop(chat_id, None)
            bot.send_message(chat_id, "↩ Đã hoàn tác giao dịch cuối.")
            send_menu(chat_id)
            return "OK"

        if data == "report":
            # Đọc dữ liệu
            main_rows = read_sheet(RANGE_MAIN)
            tools_rows = read_sheet(RANGE_TOOLS)

            main_add, main_spend, main_bal = calc_totals(main_rows)
            tools_add, tools_spend, tools_bal = calc_totals(tools_rows)

            text = f"📊 *BÁO CÁO THÁNG {datetime.datetime.utcnow().strftime('%m/%Y')}*\n\n"

            # ==== QUỸ CHÍNH ====
            text += "💰 *QUỸ CHÍNH*\n"
            text += f"• Tổng nạp: {format_money(main_add)}\n"
            text += f"• Tổng chi: {format_money(main_spend)}\n"
            text += f"• Còn lại: {format_money(main_bal)}\n\n"

            # Lịch sử nạp
            text += "➕ *Lịch sử nạp quỹ:*\n"
            has_add = False
            for r in reversed(main_rows):
                if len(r) < 3 or r[1] != "add":
                    continue
                has_add = True
                t, _, amount, desc, user = (r + ["", "", "", ""])[:5]
                text += f"  ➕ {format_money(amount)} — {desc} • {t}\n"
            if not has_add:
                text += "  Không có\n"

            # Lịch sử chi
            text += "\n➖ *Lịch sử chi tiêu:*\n"
            has_spend = False
            for r in reversed(main_rows):
                if len(r) < 3 or r[1] != "spend":
                    continue
                has_spend = True
                t, _, amount, desc, user = (r + ["", "", "", ""])[:5]
                text += f"  ➖ {format_money(amount)} — {desc} • {t}\n"
            if not has_spend:
                text += "  Không có\n"

            # ==== QUỸ DỤNG CỤ ====
            text += "\n\n🛠 *QUỸ DỤNG CỤ*\n"
            text += f"• Tổng nạp: {format_money(tools_add)}\n"
            text += f"• Tổng chi: {format_money(tools_spend)}\n"
            text += f"• Còn lại: {format_money(tools_bal)}\n\n"

            text += "➕ *Lịch sử nạp quỹ dụng cụ:*\n"
            has_add2 = False
            for r in reversed(tools_rows):
                if len(r) < 3 or r[1] != "add":
                    continue
                has_add2 = True
                t, _, amount, desc, user = (r + ["", "", "", ""])[:5]
                text += f"  ➕ {format_money(amount)} — {desc} • {t}\n"
            if not has_add2:
                text += "  Không có\n"

            text += "\n➖ *Lịch sử chi dụng cụ:*\n"
            has_spend2 = False
            for r in reversed(tools_rows):
                if len(r) < 3 or r[1] != "spend":
                    continue
                has_spend2 = True
                t, _, amount, desc, user = (r + ["", "", "", ""])[:5]
                text += f"  ➖ {format_money(amount)} — {desc} • {t}\n"
            if not has_spend2:
                text += "  Không có\n"

            bot.send_message(chat_id, text, parse_mode="Markdown")
            return "OK"

        return "OK"

    # ===== MESSAGE THƯỜNG =====
    if update.message:
        msg = update.message
        chat_id = msg.chat_id
        uid = msg.from_user.id
        text = (msg.text or "").strip()
        user_name = msg.from_user.first_name or "Không tên"

        # /start hoặc /menu
        if text.startswith("/start") or text.startswith("/menu"):
            send_menu(chat_id)
            return "OK"

        # Nếu chưa chọn chức năng -> bắt chọn
        if chat_id not in STATE:
            bot.send_message(chat_id, "⚠ Vui lòng bấm nút chức năng trước.\nGõ /start để hiện menu.")
            return "OK"

        mode = STATE[chat_id]

        # Chuẩn hóa input: tách tiền & mô tả
        parts = text.split(" ", 1)
        amount = parse_amount(parts[0])

        if amount is None:
            bot.send_message(
                chat_id,
                "⚠ Sai cấu trúc tiền.\n"
                "Ví dụ đúng: `50k rau` hoặc `100k A nộp`.\n"
                "Nhớ có chữ *k* sau số tiền.",
                parse_mode="Markdown"
            )
            return "OK"

        desc_raw = parts[1].strip() if len(parts) > 1 else ""
        if desc_raw:
            desc = f"{desc_raw} — ({user_name})"
        else:
            # Nếu không ghi chú, vẫn gắn user
            desc = f"Không ghi chú — ({user_name})"

        row = [now(), "", str(amount), desc, user_name]

        # Ghi vào sheet tương ứng
        if mode == "add_main":
            row[1] = "add"
            append_row(RANGE_MAIN, row)
            UNDO_DATA[chat_id] = {"fund": "main"}
            bot.send_message(
                chat_id,
                f"💰 NẠP {format_money(amount)}\n👉 Quỹ chính: sẽ cập nhật trong báo cáo."
            )

        elif mode == "spend_main":
            row[1] = "spend"
            append_row(RANGE_MAIN, row)
            UNDO_DATA[chat_id] = {"fund": "main"}
            bot.send_message(
                chat_id,
                f"🧾 CHI {format_money(amount)} — {desc}"
            )

        elif mode == "add_tool":
            if uid not in ADMIN_IDS:
                bot.send_message(chat_id, "⛔ Chỉ admin mới thêm quỹ dụng cụ.")
                return "OK"
            row[1] = "add"
            append_row(RANGE_TOOLS, row)
            UNDO_DATA[chat_id] = {"fund": "tool"}
            bot.send_message(
                chat_id,
                f"🛠 NẠP DỤNG CỤ {format_money(amount)}"
            )

        elif mode == "spend_tool":
            if uid not in ADMIN_IDS:
                bot.send_message(chat_id, "⛔ Chỉ admin mới chi quỹ dụng cụ.")
                return "OK"
            row[1] = "spend"
            append_row(RANGE_TOOLS, row)
            UNDO_DATA[chat_id] = {"fund": "tool"}
            bot.send_message(
                chat_id,
                f"🛠 CHI DỤNG CỤ {format_money(amount)} — {desc}"
            )

        # Sau khi xử lý xong 1 lệnh -> xoá state và gửi lại menu
        STATE.pop(chat_id, None)
        send_menu(chat_id)
        return "OK"

    return "OK"


if __name__ == "__main__":
    # Chạy local test; trên Render không dùng dòng này
    app.run(host="0.0.0.0", port=5000)
