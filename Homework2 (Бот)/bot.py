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



PROMPT_TEMPLATE = """
Проанализируй эту лабораторную работу студента и дай развернутую оценку.
КРИТЕРИИ ОЦЕНКИ (100 баллов максимум):
1. Качество кода и решения (0-30 баллов)
2. Полнота и правильность реализации (0-30 баллов)
3. Документация и комментарии (0-20 баллов)
4. Оформление и структура работы (0-20 баллов)
Дай конструктивную оценку:
- Кратко опиши, что делает работа
- Оцени каждый критерий с обоснованием
- Укажи сильные стороны
- Дай конкретные рекомендации для улучшения
- Поставь итоговую оценку из 100 баллов

Будь справедлив, но требователен. Пиши понятно для студента.
Стиль: сжатый, деловой, без лишних отступов

"""




class PromptUpdate(StatesGroup):
    waiting_for_prompt = State()

class ParamsUpdate(StatesGroup):
    waiting_for_params = State()

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
#Дефолт модель
CURRENT_MODEL = "qwen/qwen3-235b-a22b:free"
AI_PARAMS = {
    "temperature": 0.1,
    "max_tokens": 4000,
    "top_p": 1.0,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0
}
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


def get_models_keyboard():
    models = [
        "meta-llama/llama-4-maverick:free",
        "google/gemini-2.5-pro-exp-03-25:free",
        "deepseek/deepseek-chat-v3-0324:free",
        "qwen/qwen3-235b-a22b:free"  # Добавил текущую для полноты
    ]

    keyboard = []
    for model in models:
        short_name = model.split('/')[1].split(':')[0]
        keyboard.append([InlineKeyboardButton(text=f"{short_name}", callback_data=model)])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_params_button():
    params = AI_PARAMS.keys()

    keyboard = []
    for param in params:
        keyboard.append([InlineKeyboardButton(text=f"{param}", callback_data=param)])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)




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

@dp.message(Command("newmodel"))
async def select_model_command(message: Message):
    """Команда для выбора модели"""
    await message.answer(
        f"Текущая модель: \n<pre><code>{CURRENT_MODEL}</code></pre>\n\n"
        "Выберите новую модель из списка:",
        reply_markup=get_models_keyboard()
    )


@dp.message(Command("newparams"))
async def select_params_command(message: Message):
    """Команда для выбора параметра для изменения"""
    # Красиво форматируем текущие параметры для вывода
    params_text = "\n".join([f"• <code>{key}</code> = <code>{value}</code>" for key, value in AI_PARAMS.items()])

    await message.answer(
        f"<b>Текущие параметры модели:</b>\n{params_text}\n\n"
        "Выберите параметр для изменения:",
        reply_markup=get_params_button()  # Используем твою клавиатуру
    )

@dp.message(ParamsUpdate.waiting_for_params)
async def process_new_param_value(message: Message, state: FSMContext):
    """Сохранение нового значения параметра"""
    global AI_PARAMS
    user_data = await state.get_data()
    param_name = user_data.get('param_to_update')
    new_value_str = message.text

    try:
        new_value = float(new_value_str)
        AI_PARAMS[param_name] = new_value
        await message.answer(f"✅ Параметр <code>{param_name}</code> обновлен на значение <code>{new_value}</code>")
        await state.clear()
    except ValueError:
        await message.answer("❌ Ошибка. Пожалуйста, введите числовое значение (например, 0.7 или 1024).")



@dp.message(Command("newprompt"))
async def create_newprompt(message: Message, state: FSMContext):  # Добавляем state
    user_data = await state.get_data()
    current_prompt = user_data.get('user_prompt', PROMPT_TEMPLATE)

    await message.answer(
        f"<b>Ваш текущий промпт:</b>\n<pre><code>{current_prompt}</code></pre>",
        reply_markup=promt_create_button()
    )




@dp.message(PromptUpdate.waiting_for_prompt)
async def process_new_prompt(message: Message, state: FSMContext):
    """Сохранение нового промпта для конкретного пользователя"""
    new_prompt_text = message.text
    await state.update_data(user_prompt=new_prompt_text)
    await message.answer("✅ Ваш личный промпт успешно обновлен!")
    await state.clear()


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


@dp.callback_query(lambda c: ':free' in c.data)  # Ловим все callback'и, где есть ':free'
async def process_model_selection(callback_query: CallbackQuery):
    """Обработка выбора модели"""
    global CURRENT_MODEL
    new_model = callback_query.data
    CURRENT_MODEL = new_model

    short_name = new_model.split('/')[1].split(':')[0]

    await callback_query.message.edit_text(
        f"✅ Модель успешно изменена на:\n<pre><code>{short_name}</code></pre>"
    )
    await callback_query.answer()


@dp.callback_query(F.data == "np")
async def new_prompt_start(callback_query: CallbackQuery, state: FSMContext):
    """Начало обновления промпта"""
    await callback_query.message.answer("Пришлите новый текст для промпта.")
    await state.set_state(PromptUpdate.waiting_for_prompt)
    await callback_query.answer()


# Этот callback будет ловить нажатия на кнопки с параметрами
@dp.callback_query(F.data.in_(AI_PARAMS.keys()))
async def start_param_update(callback_query: CallbackQuery, state: FSMContext):
    """Начало обновления параметра"""
    param_name = callback_query.data
    await state.update_data(param_to_update=param_name)  # Сохраняем, какой параметр меняем

    await callback_query.message.answer(f"Пришлите новое значение для параметра <code>{param_name}</code>:")
    await state.set_state(ParamsUpdate.waiting_for_params)
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
async def handle_document(message: Message, state: FSMContext):
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
        result = await check_with_ai(content, state)
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

async def check_with_ai(content: str, state: FSMContext) -> str:
    """Проверка работы через OpenRouter"""
    prompt = PROMPT_TEMPLATE + f"\n\nСОДЕРЖИМОЕ РАБОТЫ:\n{content}"

    try:
        response = openrouter.chat.completions.create(
            model=CURRENT_MODEL,
            messages=[
                {"role": "user", "content": prompt}
            ],
            **AI_PARAMS
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

