### Новые возможности бота


#### 1. Загрузка промпта из файла
-  Промпт для нейросети теперь загружается из внешнего файла `prompt.txt` при старте бота.
```python
try:
    with open('prompt.txt', 'r', encoding='utf-8') as f:
        PROMPT_TEMPLATE = f.read()
except FileNotFoundError:
    print("Ошибка: Файл 'prompt.txt' не найден! Убедитесь, что он находится в той же папке.")
    exit(1)
```
-  Это позволяет менять промпт, не редактируя основной скрипт.

#### 2. Новая команда `/newprompt`
-  Добавлена команда, которая показывает текущий текст промпта в удобном для копирования виде (с помощью тегов `<pre><code>`). К этому сообщению прикрепляется кнопка "Перезаписать промпт".
```python
@dp.message(Command("newprompt"))
async def create_newprompt(message: Message):
    await message.answer(
         f"<b>Ваш промпт:</b>\n<pre><code>{PROMPT_TEMPLATE}</code></pre>",
        reply_markup=promt_create_button()
    )
```

#### 3. Механизм состояний (FSM) из aiogram
- Внедрена **машина состояний** (`StatesGroup`) для реализации многошагового диалога с пользователем.
```python
class PromptUpdate(StatesGroup):
    waiting_for_prompt = State()
```
- Благодаря этому механизму бот может войти в "режим ожидания" нового промпта после нажатия кнопки.

#### 4. Логика обновления промпта
- Написаны обработчики (`callback_query` для кнопки и `message` для состояния)
```python
@dp.callback_query(F.data == "np")
async def new_prompt_start(callback_query: CallbackQuery, state: FSMContext):
    """Начало обновления промпта"""
    await callback_query.message.answer("Пришлите новый текст для промпта.")
    await state.set_state(PromptUpdate.waiting_for_prompt)
    await callback_query.answer()
```


, которые:
  1.  Активируют "режим ожидания" после нажатия кнопки.
  2.  Принимают следующий текстовый ответ от пользователя как новый промпт.
  3.  **Перезаписывают файл** `prompt.txt` новым текстом.
  4.  Обновляют промпт в памяти бота (в переменной `PROMPT_TEMPLATE`).
  5.  Сообщают пользователю об успешном обновлении и выходят из режима ожидания.

### Итог
Теперь можно менять логику проверки ИИ, не прикасаясь к основному коду.

*P.S. Бот залит на сервер и работает 24/7 пока оплачивается сервер по ссылке [@tipislab2_bot](https://t.me/tipislab2_bot)*
