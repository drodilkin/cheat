import asyncio
import logging
import secrets
import string
from datetime import datetime, timedelta

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import LabeledPrice, PreCheckoutQuery

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8672571857:AAGUsKf4ySxbVypoy7OqhDGN9CwbJFUj8Eg"
GOOGLE_SHEET_NAME = "privet" # Точь-в-точь как в Google

# --- ПОДКЛЮЧЕНИЕ К GOOGLE TABLES ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open(GOOGLE_SHEET_NAME)

# Листы таблицы (создай их в таблице с такими именами)
users_sheet = sheet.worksheet("Users") # Столбцы: user_id, status, expires_at, trial_used
codes_sheet = sheet.worksheet("Codes") # Столбцы: code, user_id, days, used

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def generate_code():
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(10))

# --- ЛОГИКА БОТА ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = str(message.from_user.id)
    
    # Регистрация в таблице, если юзера нет
    try:
        cell = users_sheet.find(user_id)
    except gspread.exceptions.CellNotFound:
        users_sheet.append_row([user_id, "inactive", "", "FALSE"])
    
    kb = [
        [types.KeyboardButton(text="🎁 Пробный период")],
        [types.KeyboardButton(text="💎 Купить подписку")],
        [types.KeyboardButton(text="📊 Мой статус")]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.answer("Привет! Я выдаю коды доступа. Выбери действие:", reply_markup=keyboard)

@dp.message(F.text == "🎁 Пробный период")
async def get_trial(message: types.Message):
    user_id = str(message.from_user.id)
    cell = users_sheet.find(user_id)
    user_data = users_sheet.row_values(cell.row)
    
    # user_data[3] — это столбец trial_used
    if len(user_data) > 3 and user_data[3] == "TRUE":
        return await message.answer("Ошибка: Вы уже использовали пробный период.")
    
    code = generate_code()
    # Записываем код в лист Codes
    codes_sheet.append_row([code, user_id, "1", "FALSE"])
    # Помечаем в Users, что триал использован
    users_sheet.update_cell(cell.row, 4, "TRUE")
    
    await message.answer(f"Ваш пробный код на 24 часа:\n`{code}`", parse_mode="MarkdownV2")

@dp.message(F.text == "💎 Купить подписку")
async def buy_menu(message: types.Message):
    kb = [
        [types.InlineKeyboardButton(text="1 месяц (50 Stars)", callback_data="buy_1m")],
        [types.InlineKeyboardButton(text="1 год (100 Stars)", callback_data="buy_1y")]
    ]
    await message.answer("Выберите тариф:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

# Обработка выбора тарифа и выставление счета
@dp.callback_query(F.data.startswith("buy_"))
async def send_invoice(callback: types.CallbackQuery):
    plan = callback.data.split("_")[1]
    price = 50 if plan == "1m" else 100
    label = "Подписка 1 месяц" if plan == "1m" else "Подписка 1 год"
    
    await callback.message.answer_invoice(
        title=label,
        description=f"Получение уникального кода на {label}",
        prices=[LabeledPrice(label="XTR", amount=price)],
        provider_token="", # Для Stars пусто
        payload=f"pay_{plan}",
        currency="XTR"
    )
    await callback.answer()

# Подтверждение возможности оплаты
@dp.pre_checkout_query()
async def checkout(pre_query: PreCheckoutQuery):
    await pre_query.answer(ok=True)

# Успешная оплата
@dp.message(F.success_payment)
async def success_pay(message: types.Message):
    payload = message.success_payment.invoice_payload
    days = 30 if "1m" in payload else 365
    
    code = generate_code()
    codes_sheet.append_row([code, str(message.from_user.id), str(days), "FALSE"])
    
    await message.answer(f"Оплата принята! 🎉\nВаш код доступа:\n`{code}`", parse_mode="MarkdownV2")

# Запуск
async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
