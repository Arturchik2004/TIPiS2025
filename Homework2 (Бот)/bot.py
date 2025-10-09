"""
Простейший Telegram бот для проверки лабораторных работ через OpenRouter
"""

import asyncio
import os
import tempfile
from pathlib import Path
import re

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from dotenv import load_dotenv
from openai import OpenAI

from file_utils import extract_docx, extract_pdf, extract_txt
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup





# Загрузка переменных окружения
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

# Добавил возможность вынести промпт в отдельный файл)
try:
    with open('prompt.txt', 'r', encoding='utf-8') as f:
        PROMPT_TEMPLATE = f.read()
except FileNotFoundError:
    print("Ошибка: Файл 'prompt.txt' не найден! Убедитесь, что он находится в той же папке.")
    exit(1)




class PromptUpdate(StatesGroup):
    waiting_for_prompt = State()



if not BOT_TOKEN or not OPENROUTER_KEY:
    print("Добавьте токены в .env файл!")
    exit(1)

# Инициализация
bot = Bot(
    token=BOT_TOKEN, 
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# OpenRouter клиент
openrouter = OpenAI(
    api_key=OPENROUTER_KEY,
    base_url="https://openrouter.ai/api/v1"
)

# Поддерживаемые форматы
SUPPORTED_FORMATS = ['.pdf', '.docx', '.txt']
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 МБ

def get_main_keyboard():
    """Главная клавиатура"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ])

def promt_create_button():
    """Главная клавиатура"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❓ Перезаписать промпт", callback_data="np")]
    ])

@dp.message(CommandStart())
async def start_command(message: Message):
    """Команда /start"""
    await message.answer(
        f"🎓 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        "Я проверяю лабораторные работы с помощью ИИ.\n\n"
        "📄 <b>Как пользоваться:</b>\n"
        "Просто отправь мне файл с работой!\n\n"
        "📁 <b>Поддерживаю:</b> PDF, DOCX, TXT файлы (до 20 МБ)\n"
        "🤖 <b>Использую:</b> Claude 3.5 Sonnet\n\n",
        reply_markup=get_main_keyboard()
    )

@dp.message(Command("newprompt"))
async def create_newprompt(message: Message):
    """Команда /help"""
    await message.answer(
         f"📖 <b>Ваш промпт:</b>\n<pre><code>{PROMPT_TEMPLATE}</code></pre>",
        reply_markup=promt_create_button()
    )


@dp.message(PromptUpdate.waiting_for_prompt)
async def process_new_prompt(message: Message, state: FSMContext):
    """Сохранение нового промпта"""
    global PROMPT_TEMPLATE
    new_prompt_text = message.text

    # Сохраняем в файл
    with open('prompt.txt', 'w', encoding='utf-8') as f:
        f.write(new_prompt_text)

    # Обновляем в переменной
    PROMPT_TEMPLATE = new_prompt_text

    await message.answer("✅ Промпт успешно обновлен!")
    await state.clear()  # Выходим из состояния


@dp.message(Command("help"))
async def help_command(message: Message):
    """Команда /help"""
    await message.answer(
        "📖 <b>Как пользоваться ботом:</b>\n\n"
        "1️⃣ Отправь мне файл с лабораторной работой\n"
        "2️⃣ Жди проверку от ИИ (1-2 минуты)\n"
        "3️⃣ Получи детальную оценку\n\n"
        "<b>📁 Поддерживаемые форматы:</b>\n"
        "• PDF (до 20 МБ)\n"
        "• DOCX (Microsoft Word)\n"
        "• TXT (текстовые файлы)\n\n"
        "<b>📊 Что проверяется:</b>\n"
        "• Качество кода и решения\n"
        "• Полнота документации\n" 
        "• Правильность выводов\n"
        "• Оформление работы\n\n"
        "<b>💡 Результат:</b> Оценка из 100 баллов + рекомендации",
        reply_markup=get_main_keyboard()
    )

@dp.callback_query(F.data == "help")
async def help_callback(callback):
    """Помощь через callback"""
    await help_command(callback.message)





@dp.callback_query(F.data == "newprompt")
async def new_prompt(callback):
    """Помощь через callback"""
    await create_newprompt(callback.message)

@dp.callback_query(F.data == "np") # Изменил "newprompt" на "np" для краткости
async def new_prompt_start(callback_query: CallbackQuery, state: FSMContext):
    """Начало обновления промпта"""
    await callback_query.message.answer("Пришлите новый текст для промпта.")
    await state.set_state(PromptUpdate.waiting_for_prompt)
    await callback_query.answer()

@dp.message(F.text & ~F.text.startswith('/'))
async def handle_text(message: Message):
    """Обработка текстовых сообщений"""
    await message.answer(
        "📄 <b>Отправь файл для проверки!</b>\n\n"
        "Я не анализирую текстовые сообщения.\n"
        "Просто прикрепи файл с лабораторной работой.\n\n"
        "Поддерживаю: PDF, DOCX, TXT",
        reply_markup=get_main_keyboard()
    )





@dp.message(F.document)
async def handle_document(message: Message):
    """Обработка файла"""
    document = message.document
    file_name = document.file_name
    file_size = document.file_size
    
    # Проверка размера
    if file_size > MAX_FILE_SIZE:
        await message.answer(
            f"❌ <b>Файл слишком большой!</b>\n\n"
            f"📏 Размер файла: {file_size / 1024 / 1024:.1f} МБ\n"
            f"📏 Максимум: {MAX_FILE_SIZE / 1024 / 1024} МБ\n\n"
            f"Попробуй сжать файл или выбрать другой.",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Проверка формата
    file_ext = Path(file_name).suffix.lower()
    if file_ext not in SUPPORTED_FORMATS:
        await message.answer(
            f"❌ <b>Неподдерживаемый формат!</b>\n\n"
            f"📄 Твой файл: <code>{file_ext}</code>\n"
            f"📁 Поддерживаю: <code>{', '.join(SUPPORTED_FORMATS)}</code>\n\n"
            f"Преобразуй файл в подходящий формат.",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Показываем статус обработки
    status_msg = await message.answer(
        "⏳ <b>Проверяю работу...</b>\n\n"
        "🔄 Загружаю файл\n"
        "⏳ Извлекаю содержимое\n"
        "⏳ Анализирую с помощью ИИ\n\n"
        "<i>Обычно занимает 1-2 минуты</i>"
    )
    
    temp_path = None
    
    try:
        # Загружаем файл
        file = await bot.get_file(document.file_id)
        
        # Создаем временный файл
        with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as tmp_file:
            await bot.download_file(file.file_path, tmp_file.name)
            temp_path = tmp_file.name
        
        await status_msg.edit_text(
            "⏳ <b>Проверяю работу...</b>\n\n"
            "✅ Файл загружен\n"
            "🔄 Извлекаю содержимое\n"
            "⏳ Анализирую с помощью ИИ"
        )
        
        # Извлекаем содержимое в зависимости от типа файла
        if file_ext == '.txt':
            content = await extract_txt(temp_path)
        elif file_ext == '.docx':
            content = await extract_docx(temp_path)
        elif file_ext == '.pdf':
            content = await extract_pdf(temp_path)
        else:
            raise Exception("Неподдерживаемый формат")
        
        # Проверяем, что содержимое не пустое
        if not content.strip():
            raise Exception("Файл пуст или не содержит читаемого текста")
        
        await status_msg.edit_text(
            "⏳ <b>Проверяю работу...</b>\n\n"
            "✅ Файл загружен\n"
            "✅ Содержимое извлечено\n"
            "🔄 Анализирую с помощью ИИ\n\n"
            "<i>ИИ анализирует работу...</i>"
        )
        
        # Отправляем на проверку
        result = await check_with_ai(content)
        
        # Удаляем временный файл
        if temp_path:
            os.unlink(temp_path)
        
        # Отправляем информацию о файле
        await status_msg.edit_text(
            "✅ <b>Проверка завершена!</b>\n\n"
            f"📄 <b>Файл:</b> <code>{file_name}</code>\n"
            f"📊 <b>Размер:</b> {file_size / 1024:.1f} КБ\n"
            f"📝 <b>Символов:</b> {len(content):,}\n"
            f"🤖 <b>Модель:</b> Claude 3.5 Sonnet"
        )
        
        # Разбиваем длинный результат на части (Telegram ограничение 4096 символов)
        if len(result) > 4000:
            parts = [result[i:i+4000] for i in range(0, len(result), 4000)]
            for i, part in enumerate(parts):
                if i == 0:
                    await message.answer(f"📋 <b>Результат проверки:</b>\n\n{part}")
                else:
                    await message.answer(f"📋 <b>Продолжение ({i+1}):</b>\n\n{part}")
        else:
            await message.answer(f"📋 <b>Результат проверки:</b>\n\n{result}")
        
        # Предлагаем проверить еще файл
        await message.answer(
            "🎉 <b>Готово!</b>\n\n"
            "Можешь отправить еще один файл для проверки 📄",
            reply_markup=get_main_keyboard()
        )
        
    except Exception as e:
        # Удаляем временный файл в случае ошибки
        if temp_path:
            try:
                os.unlink(temp_path)
            except:
                pass
        
        await status_msg.edit_text(
            f"❌ <b>Ошибка при обработке файла:</b>\n\n"
            f"<code>{str(e)}</code>\n\n"
            f"Попробуй еще раз или выбери другой файл.",
            reply_markup=get_main_keyboard()
        )

async def check_with_ai(content: str) -> str:
    """Проверка работы через OpenRouter"""
    prompt = PROMPT_TEMPLATE + f"\n\nСОДЕРЖИМОЕ РАБОТЫ:\n{content}"

    try:
        response = openrouter.chat.completions.create(
            model="qwen/qwen3-235b-a22b:free",
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=4000,
            temperature=0.1
        )


        raw_content = response.choices[0].message.content
        cleaned_content = re.sub(r'<[^>]+>', '', raw_content).strip()
        return cleaned_content

    except Exception as e:
        return f"❌ Ошибка при обращении к ИИ: {str(e)}\n\nПопробуйте еще раз через несколько минут."

# Запуск бота
async def main():
    print("🤖 Запускаю бот для проверки лабораторных работ...")
    print("📄 Поддерживаемые форматы: PDF, DOCX, TXT")
    print("🤖 ИИ модель: Claude 3.5 Sonnet")
    print("⚡ Просто отправьте файл для проверки!")
    print("-" * 50)
    
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        print("\n Бот остановлен пользователем")
    except Exception as e:
        print(f"\n Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())

