# Новые возможности бота

Бот получил три новые команды для гибкой настройки его поведения прямо из чата Telegram. Это стало возможным благодаря внедрению механизма состояний (FSM).

### Динамический выбор AI-модели (`/newmodel`)

Теперь вы можете переключаться между различными моделями LLM, доступными на OpenRouter.

**Как это работает:**
Команда `/newmodel` отправляет пользователю клавиатуру со списком доступных моделей. Выбор модели обновляет глобальную переменную `CURRENT_MODEL`, которая используется для всех последующих запросов к API.

**Пример кода:**
##### Глобальная переменная для хранения текущей модели
```python
CURRENT_MODEL = "qwen/qwen3-235b-a22b:free"
```
##### Функция для создания клавиатуры с моделями
```python
def get_models_keyboard():
    models = [
        "meta-llama/llama-4-maverick:free",
        "google/gemini-2.5-pro-exp-03-25:free",
        "deepseek/deepseek-chat-v3-0324:free",
        "qwen/qwen3-235b-a22b:free"
    ]
    keyboard = []
    for model in models:
        short_name = model.split('/')[1].split(':')[0]
        keyboard.append([InlineKeyboardButton(text=f"{short_name}", callback_data=model)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
```
##### Обработчик команды /newmodel
```python
@dp.message(Command("newmodel"))
async def select_model_command(message: Message):
    """Команда для выбора модели"""
    await message.answer(
        f"Текущая модель: \n<pre><code>{CURRENT_MODEL}</code></pre>\n\n"
        "Выберите новую модель из списка:",
        reply_markup=get_models_keyboard()
    )
```
##### Обработчик нажатия на кнопку с моделью
```python
@dp.callback_query(lambda c: ':free' in c.data)
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
```
### Настройка параметров AI (/newparams)
Появилась возможность тонкой настройки параметров AI, таких как temperature (креативность) или max_tokens (длина ответа).
Команда /newparams запускает пошаговый сценарий с использованием FSM. Бот сначала предлагает выбрать параметр для изменения, а затем запрашивает новое значение и сохраняет его в глобальный словарь AI_PARAMS.
##### Глобальный словарь с параметрами
```python

AI_PARAMS = {
    "temperature": 0.1,
    "max_tokens": 4000,
    "top_p": 1.0,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0
}
```
##### FSM состояния
```python
class ParamsUpdate(StatesGroup):
    waiting_for_params = State()
```
##### Обработчик команды /newparams
```python
@dp.message(Command("newparams"))
async def select_params_command(message: Message):
    """Команда для выбора параметра для изменения"""
    params_text = "\n".join([f"• <code>{key}</code> = <code>{value}</code>" for key, value in AI_PARAMS.items()])
    await message.answer(
        f"<b>Текущие параметры модели:</b>\n{params_text}\n\n"
        "Выберите параметр для изменения:",
        reply_markup=get_params_button()
    )
```
##### Обработчик, ожидающий новое значение параметра от пользователя
```python
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
```
###  Пользовательский промпт (/newprompt)
Теперь можно полностью заменить стандартную инструкцию для AI на свою собственную.
Команда /newprompt также использует FSM. Бот показывает текущий промпт и предлагает ввести новый. Новый текст сохраняется в контексте FSM для конкретного пользователя.

Пример кода:
##### Шаблон промпта по умолчанию
```python
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
```
##### FSM состояния
```python
class PromptUpdate(StatesGroup):
    waiting_for_prompt = State()
```
##### Начало диалога для смены промпта
```python
@dp.callback_query(F.data == "np")
async def new_prompt_start(callback_query: CallbackQuery, state: FSMContext):
    """Начало обновления промпта"""
    await callback_query.message.answer("Пришлите новый текст для промпта.")
    await state.set_state(PromptUpdate.waiting_for_prompt)
    await callback_query.answer()
```
##### Сохранение нового промпта
```python
@dp.message(PromptUpdate.waiting_for_prompt)
async def process_new_prompt(message: Message, state: FSMContext):
    """Сохранение нового промпта для конкретного пользователя"""
    new_prompt_text = message.text
    await state.update_data(user_prompt=new_prompt_text)
    await message.answer("✅ Ваш личный промпт успешно обновлен!")
    await state.clear()
```
# Итог
Бот запущен на сервере и работает 24/7 (пока оплачивается сервер)
[https://t.me/tipislab2_bot](https://t.me/tipislab2_bot)
