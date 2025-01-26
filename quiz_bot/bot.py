# python bot.py
import os
import json
import random
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

API_TOKEN = ''


def init_db():
    # Удалена дублирующая функция init_db
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            balance INTEGER DEFAULT 10
        )
    ''')
    conn.commit()
    conn.close()


def load_quizzes():
    quizzes = {}
    for filename in os.listdir('quizzes'):
        if filename.endswith('.json'):
            with open(os.path.join('quizzes', filename), 'r', encoding='utf-8') as f:
                quizzes[filename[:-5]] = json.load(f)
    return quizzes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Проверяем, является ли обновление запросом обратного вызова
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text='Добро пожаловать! ')
    else:
        # Если это не запрос обратного вызова, используем update.message
        await update.message.reply_text('Добро пожаловать! ')

    keyboard = [
        [InlineKeyboardButton("Регистрация", callback_data='register')],
        [InlineKeyboardButton("Вход", callback_data='login')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем сообщение с клавиатурой
    if update.callback_query:
        await update.callback_query.message.reply_text(' Пожалуйста, выберите действие:',
                                                       reply_markup=reply_markup)
    else:
        await update.message.reply_text(' Пожалуйста, выберите действие:', reply_markup=reply_markup)


# Обработчик регистрации
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text="Введите новый логин:")
    context.user_data['register_step'] = 'username'


# Обработчик ввода логина
async def process_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get('register_step') == 'username':
        context.user_data['username'] = update.message.text
        await update.message.reply_text("Введите новый пароль:")
        context.user_data['register_step'] = 'password'
    elif context.user_data.get('register_step') == 'password':
        username = context.user_data['username']
        password = update.message.text
        # Проверка на существование пользователя
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        if cursor.fetchone() is not None:
            await update.message.reply_text("Пользователь с таким логином уже существует. Попробуйте другой.")
        else:
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            await update.message.reply_text("Регистрация успешна! Теперь Вы можете войти.")
            await start_quiz(update, context)
        conn.close()
        del context.user_data['register_step']


async def process_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    username = context.user_data.get('username')  # Получаем имя пользователя из user_data
    password = update.message.text  # Получаем пароль из сообщения
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    if user is None:
        await update.message.reply_text("Неправильный логин или пароль. Попробуйте снова.")
    else:
        context.user_data['balance'] = user[2]
        await update.message.reply_text("Вход успешен! Выберите квиз.")
        await start_quiz(update, context)
    conn.close()


async def login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(text="Введите логин:")
    context.user_data['login_step'] = 'username'


async def handle_username_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get('login_step') == 'username':
        context.user_data['username'] = update.message.text
        await update.message.reply_text("Введите пароль:")
        context.user_data['login_step'] = 'password'
    elif context.user_data.get('login_step') == 'password':
        await process_login(update, context)


async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    quizzes = load_quizzes()
    if not quizzes:
        await update.message.reply_text('Нет доступных квизов.')
        return

    keyboard = [
        [InlineKeyboardButton(quiz, callback_data=f'quiz:{quiz}')] for quiz in quizzes
    ]
    keyboard.append([InlineKeyboardButton("Выход", callback_data='exit_game')])  # Кнопка выхода
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем сообщение с клавиатурой
    if update.callback_query:
        await update.callback_query.message.reply_text('Пожалуйста, выберите квиз:', reply_markup=reply_markup)
    else:
        await update.message.reply_text('Пожалуйста, выберите квиз:', reply_markup=reply_markup)

async def quiz_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == 'return_start':
        await start(update, context)
        return

    quiz_name = query.data.split(':')[1]
    quizzes = load_quizzes()
    if quiz_name not in quizzes:
        await query.message.reply_text('Квиз не найден.')
        return

    questions = random.sample(quizzes[quiz_name], min(20, len(quizzes[quiz_name])))
    context.user_data['current_quiz'] = quiz_name
    context.user_data['questions'] = questions
    context.user_data['answers'] = []
    context.user_data['current_question'] = 0
    await ask_question(update, context)


async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    questions = context.user_data['questions']
    if context.user_data['current_question'] < len(questions):
        question = questions[context.user_data['current_question']]
        keyboard = [[InlineKeyboardButton(answer, callback_data=f'answer:{answer}')] for answer in question['options']]
        keyboard.append([InlineKeyboardButton("Вернуться на старт", callback_data='return_start')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        if isinstance(update, Update) and update.callback_query:
            await update.callback_query.edit_message_text(text=question['question'], reply_markup=reply_markup)
        else:
            await update.message.reply_text(text=question['question'], reply_markup=reply_markup)
    else:
        await show_results(update, context)


async def answer_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_answer = query.data.split(':')[1]

    questions = context.user_data['questions']
    if context.user_data['current_question'] < len(questions):
        correct_answer = questions[context.user_data['current_question']]['correct_answer']
        context.user_data['answers'].append((questions[context.user_data['current_question']], user_answer))
        context.user_data['current_question'] += 1

        # Обновление баланса
        if user_answer == correct_answer:
            context.user_data['balance'] += 2
        else:
            context.user_data['balance'] -= 1

        await ask_question(update, context)
    else:
        await show_results(update, context)


async def show_results(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    results = context.user_data['answers']
    correct_count = sum(1 for question, user_answer in results if user_answer == question['correct_answer'])
    total_count = len(results)

    message = f"Вы ответили правильно на {correct_count} из {total_count} вопросов.\n"
    message += f"Ваш новый баланс: {context.user_data['balance']} баллов.\n"
    keyboard = [
        [InlineKeyboardButton("Показать ответы", callback_data='show_answers')],
        [InlineKeyboardButton("Вернуться на старт", callback_data='return_start')],
        [InlineKeyboardButton("Выход", callback_data='exit_game')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text=message, reply_markup=reply_markup)


async def show_answers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    results = context.user_data['answers']
    message = "Ваши ответы:\n"
    for question, user_answer in results:
        message += f"Вопрос: {question['question']}\nВаш ответ: {user_answer}\nПравильный ответ: {question['correct_answer']}\n\n"
    message += "Нажмите /start для возврата в главное меню."

    keyboard = [
        [InlineKeyboardButton("Выход", callback_data='exit_game')],
        [InlineKeyboardButton("Ещё", callback_data='return_start')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text=message, reply_markup=reply_markup)


async def exit_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.edit_message_text(text="Спасибо за игру! До свидания!")


def main() -> None:
    init_db()
    application = ApplicationBuilder().token(API_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(login, pattern='login'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_username_input))
    application.add_handler(CallbackQueryHandler(register, pattern='register'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_registration))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_login))

    application.add_handler(CallbackQueryHandler(quiz_selection, pattern=r'^quiz:.+'))
    application.add_handler(CallbackQueryHandler(answer_question, pattern=r'^answer:.+'))
    application.add_handler(CallbackQueryHandler(show_answers, pattern='show_answers'))
    application.add_handler(CallbackQueryHandler(start_quiz, pattern='return_start'))
    application.add_handler(CallbackQueryHandler(exit_game, pattern='exit_game'))

    application.run_polling()


if __name__ == '__main__':
    main()
