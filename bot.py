import os
import json
import datetime
from flask import Flask, request
import telegram
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from fpdf import FPDF

@app.route("/ping")
def ping():
    return "pong", 200

TOKEN = os.getenv("BOT_TOKEN")
bot = telegram.Bot(token=TOKEN)

app = Flask(__name__)

DATA_FILE = "data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"quy": 0, "lich_su": []}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


    from openpyxl import Workbook

def generate_excel(data):
    wb = Workbook()
    ws = wb.active
    ws.title = "BaoCao"

    ws.append(["Thời gian", "Loại", "Số tiền", "Mô tả", "Người nhập"])

    for item in data["lich_su"]:
        ws.append([item["time"], item["type"], item["amount"], item["desc"], item["user"]])

    filename = f"Bao_cao_{datetime.datetime.now().strftime('%Y%m')}.xlsx"
    wb.save(filename)
    return filename


def generate_pdf(data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(200, 10, txt="Báo cáo chi tiêu", ln=True, align='C')

    for item in data["lich_su"]:
        line = f"{item['time']} | {item['type']} | {item['amount']} | {item['desc']} | {item['user']}"
        pdf.cell(0, 10, txt=line, ln=True)

    filename = f"Bao_cao_{datetime.datetime.now().strftime('%Y%m')}.pdf"
    pdf.output(filename)
    return filename


def send_menu(chat_id):
    buttons = [
        [InlineKeyboardButton("➕ Thêm quỹ", callback_data="add_quy")],
        [InlineKeyboardButton("➖ Chi tiêu", callback_data="chi_tieu")],
        [InlineKeyboardButton("📊 Báo cáo tháng", callback_data="baocao")],
        [InlineKeyboardButton("📁 Xuất file", callback_data="export")],
        [InlineKeyboardButton("🧾 Lịch sử mới nhất", callback_data="history")],
    ]
    bot.send_message(chat_id, "Chọn chức năng:", reply_markup=InlineKeyboardMarkup(buttons))


@app.route("/", methods=["GET"])
def home():
    return "BepCongVu Bot is running!"


@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = telegram.Update.de_json(request.get_json(), bot)

    if update.callback_query:
        chat_id = update.callback_query.message.chat_id
        user = update.callback_query.from_user.first_name
        data = update.callback_query.data

        if data == "add_quy":
            bot.send_message(chat_id, "Nhập số tiền muốn thêm:")
            return "OK"

        elif data == "chi_tieu":
            bot.send_message(chat_id, "Nhập số tiền + mô tả (VD: 50000 mua rau):")
            return "OK"

        elif data == "history":
            data_file = load_data()
            msg = "\n".join([f"{i['time']} - {i['amount']} - {i['desc']} ({i['user']})" for i in data_file["lich_su"][-5:]])
            bot.send_message(chat_id, msg if msg else "Chưa có dữ liệu.")
            return "OK"

        elif data == "baocao":
            data_file = load_data()
            total_add = sum(i["amount"] for i in data_file["lich_su"] if i["type"] == "add")
            total_spend = sum(i["amount"] for i in data_file["lich_su"] if i["type"] == "spend")

            bot.send_message(chat_id,
                             f"📊 Báo cáo tháng:\n\n"
                             f"💰 Nạp quỹ: {total_add}\n"
                             f"🛒 Chi tiêu: {total_spend}\n"
                             f"💵 Còn lại: {data_file['quy']}")
            return "OK"

        elif data == "export":
            data_file = load_data()
            excel = generate_excel(data_file)
            pdf = generate_pdf(data_file)

            bot.send_document(chat_id, open(excel, "rb"))
            bot.send_document(chat_id, open(pdf, "rb"))
            return "OK"

    if update.message:
        chat_id = update.message.chat_id
        txt = update.message.text
        user = update.message.from_user.first_name

        if txt.startswith("/start"):
            send_menu(chat_id)
            return "OK"

        # Add money if user types number only
        if txt.isdigit():
            amount = int(txt)
            data = load_data()
            data["quy"] += amount
            data["lich_su"].append({
                "time": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
                "type": "add",
                "amount": amount,
                "desc": "Nạp quỹ",
                "user": user
            })
            save_data(data)
            bot.send_message(chat_id, f"✔ Thêm {amount} thành công.\n💰 Quỹ còn: {data['quy']}")
            return "OK"

        # Handle spending
        parts = txt.split(" ", 1)
        if len(parts) == 2 and parts[0].isdigit():
            amount = int(parts[0])
            desc = parts[1]

            data = load_data()
            data["quy"] -= amount
            data["lich_su"].append({
                "time": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
                "type": "spend",
                "amount": amount,
                "desc": desc,
                "user": user
            })
            save_data(data)
            bot.send_message(chat_id, f"🧾 Chi {amount} ({desc}) — bởi {user}\n💰 Còn: {data['quy']}")
            return "OK"

    return "OK"


