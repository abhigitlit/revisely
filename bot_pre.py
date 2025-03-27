import os
import json
import random
import traceback
import sqlite3
import aiohttp
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, PollAnswerHandler, MessageHandler,
    filters, ContextTypes, PollHandler
)
from datetime import datetime, timedelta

# Global configuration settings
CONFIG = {
    "QUIZ_DIRECTORY": "quiz",
    "DB_PATH": "quiz_bot.db",
    "MAX_QUIZ_ATTEMPTS_PER_HOUR": 2,
    "QUIZ_BLOCK_DURATION_HOURS": 1,
    "QUIZ_TIMER_SECONDS": 5,
    "MAX_CUSTOM_QUESTION_LIMIT_TRIES": 5,
    "ADMIN_USER_ID": 7800319092
}

QUIZ_DIRECTORY = CONFIG["QUIZ_DIRECTORY"]
user_data = {}

# -------------------- DATABASE SETUP --------------------
DB_PATH = "quiz_bot.db"

def init_db():
    """Initializes the SQLite database and creates necessary tables."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    # Create table to store aggregated user stats.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY,
            total_quiz_attempted INTEGER DEFAULT 0,
            total_questions_attempted INTEGER DEFAULT 0,
            total_right INTEGER DEFAULT 0,
            total_wrong INTEGER DEFAULT 0,
            block_until DATETIME
        )
    ''')
    # Create table to store individual quiz attempts timestamps.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quiz_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            quiz_timestamp DATETIME
        )
    ''')
    conn.commit()
    return conn

db_conn = init_db()

def get_user_stats(user_id):
    """Retrieves a user's stats; if not exists, creates a default row."""
    cursor = db_conn.cursor()
    cursor.execute("SELECT * FROM user_stats WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute("INSERT INTO user_stats (user_id) VALUES (?)", (user_id,))
        db_conn.commit()
        return {"user_id": user_id, "total_quiz_attempted": 0, "total_questions_attempted": 0,
                "total_right": 0, "total_wrong": 0, "block_until": None}
    else:
        # row: (user_id, total_quiz_attempted, total_questions_attempted, total_right, total_wrong, block_until)
        return {"user_id": row[0], "total_quiz_attempted": row[1], "total_questions_attempted": row[2],
                "total_right": row[3], "total_wrong": row[4], "block_until": row[5]}

def update_user_stats(user_id, quiz_attempted, questions_attempted, right, wrong):
    """Updates a user's stats after a quiz."""
    cursor = db_conn.cursor()
    cursor.execute('''
        UPDATE user_stats
        SET total_quiz_attempted = total_quiz_attempted + ?,
            total_questions_attempted = total_questions_attempted + ?,
            total_right = total_right + ?,
            total_wrong = total_wrong + ?
        WHERE user_id = ?
    ''', (quiz_attempted, questions_attempted, right, wrong, user_id))
    db_conn.commit()

def record_quiz_attempt(user_id, timestamp):
    """Records a quiz attempt timestamp in the database."""
    cursor = db_conn.cursor()
    cursor.execute("INSERT INTO quiz_attempts (user_id, quiz_timestamp) VALUES (?, ?)", (user_id, timestamp))
    db_conn.commit()

def set_user_block(user_id, block_until):
    """Sets the block_until field for a user."""
    cursor = db_conn.cursor()
    cursor.execute("UPDATE user_stats SET block_until = ? WHERE user_id = ?", (block_until, user_id))
    db_conn.commit()

def count_recent_attempts(user_id, since_time):
    """Counts how many quizzes the user started since a given timestamp."""
    cursor = db_conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM quiz_attempts WHERE user_id = ? AND quiz_timestamp > ?", (user_id, since_time))
    count = cursor.fetchone()[0]
    return count

# -------------------- TELEGRAM BOT FUNCTIONS --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    now = datetime.utcnow()

    if context.user_data.get("active", False):
        #await update.message.reply_text("⚠️ You already have an active quiz. Finish it first before starting a new one.")
        return
    if user_id != CONFIG["ADMIN_USER_ID"]:
        user_stats = get_user_stats(user_id)
        
        # Check if user is blocked
        if user_stats["block_until"]:
            block_until = datetime.strptime(user_stats["block_until"], "%Y-%m-%d %H:%M:%S")
            if now < block_until:
                return
        
        # Count quiz attempts in the past hour.
        one_hour_ago = now - timedelta(hours=1)
        attempts = count_recent_attempts(user_id, one_hour_ago.strftime("%Y-%m-%d %H:%M:%S"))
        if attempts >= CONFIG["MAX_QUIZ_ATTEMPTS_PER_HOUR"]:
            block_until_time = now + timedelta(CONFIG["QUIZ_BLOCK_DURATION_HOURS"])
            set_user_block(user_id, block_until_time.strftime("%Y-%m-%d %H:%M:%S"))
            await update.message.reply_text("❌ You have reached your quiz limit (2 per hour). Try after 1h")
            return
        
        # Record the new quiz attempt.
        record_quiz_attempt(user_id, now.strftime("%Y-%m-%d %H:%M:%S"))

    # Continue with normal quiz selection.
    context.user_data["active"] = True  
    context.user_data["current_path"] = QUIZ_DIRECTORY

    if not os.path.exists(QUIZ_DIRECTORY):
        os.makedirs(QUIZ_DIRECTORY)

    await show_directory(chat_id, context)


async def quit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /quit cancels the ongoing quiz only if there is an active quiz.
    It stops the poll, cancels any scheduled jobs, updates the database with
    the user's current progress, and clears the session data.
    """
    user_id = update.message.from_user.id

    if user_id in user_data and user_data[user_id].get("active_quiz", False):
        chat_id = user_data[user_id].get("chat_id")
        poll_message_id = user_data[user_id].get("poll_message_id")
        if poll_message_id:
            try:
                await context.bot.stop_poll(chat_id=chat_id, message_id=poll_message_id)
            except Exception as e:
                print(f"Failed to stop poll: {e}")
        
        # Cancel any scheduled timeout jobs for the quiz.
        current_jobs = context.job_queue.get_jobs_by_name(f"quiz_{user_id}")
        for job in current_jobs:
            job.schedule_removal()
        
        # Update user stats with the progress made so far, if any.
        stats = user_data[user_id]
        attempted = stats.get("attempted", 0)
        if attempted > 0:
            update_user_stats(
                user_id,
                quiz_attempted=1,  # Count this quit session as an attempt.
                questions_attempted=attempted,
                right=stats.get("correct", 0),
                wrong=attempted - stats.get("correct", 0)
            )
        
        user_data[user_id]["active_quiz"] = False
        del user_data[user_id]
        context.user_data["active"] = False
        
        await update.message.reply_text("Your active quiz has been canceled.You can start a new quiz with /start.")
    else:
        pass


def contains_json(path):
    for root, _, files in os.walk(path):
        if any(f.endswith(".json") for f in files):
            return True
    return False

async def show_directory(chat_id, context: ContextTypes.DEFAULT_TYPE, query=None):
    """Displays directories and quiz files using an inline keyboard in a 2×2 format."""
    current_path = context.user_data.get("current_path", QUIZ_DIRECTORY)
    items = os.listdir(current_path)

    # Separate directories and JSON files
    dirs = [item for item in items if os.path.isdir(os.path.join(current_path, item))]
    files = [item for item in items if item.endswith(".json")]

    buttons = []
    inline_items = []  # Temporary list to store buttons for 2×2 format

    # Add directories (📁 Folder Name)
    for d in dirs:
        dir_path = os.path.join(current_path, d)
        if contains_json(dir_path):  # Show only directories with JSON files
            inline_items.append(InlineKeyboardButton(f"📁 {d}", callback_data=f"dir:{d}"))

    # Add files (📝 File Name)
    for f in files:
        inline_items.append(InlineKeyboardButton(f"📝 {f[:-5]}", callback_data=f"file:{f}"))

    # Convert inline_items into 2×2 grid
    for i in range(0, len(inline_items), 2):
        buttons.append(inline_items[i:i+2])  # Take two items per row

    # Check if the user is in the home directory
    is_home = os.path.abspath(current_path) == os.path.abspath(QUIZ_DIRECTORY)

    # Add "⬅️ Previous" and "🏠 Home" buttons (only if not at home)
    if not is_home:
        buttons.append([
            InlineKeyboardButton("⬅️ Previous", callback_data="dir:.."),
            InlineKeyboardButton("🏠 Home", callback_data="home")
        ])

    # If no files or directories are found, display a message
    if not inline_items and is_home:
        if query:
            await query.edit_message_text("No directories or quiz files found.")
        else:
            await context.bot.send_message(chat_id, "No directories or quiz files found.")
        return

    # Send or edit the message
    message_text = "📂 Select a Quiz"
    reply_markup = InlineKeyboardMarkup(buttons)
    if query:
        await query.edit_message_text(message_text, reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id, message_text, reply_markup=reply_markup)

async def quiz_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles inline keyboard callbacks for directory navigation and file selection."""
    query = update.callback_query
    user_id = query.from_user.id
    current_time = datetime.utcnow()

    # Prevent multiple taps within 2 seconds
    last_tap_time = context.user_data.get(f"last_tap_{user_id}")
    if last_tap_time and (current_time - last_tap_time).total_seconds() < 2:
        await query.answer("⏳ You need to tap once only", show_alert=False)
        return  # Ignore this tap

    # Update last tap time
    context.user_data[f"last_tap_{user_id}"] = current_time
    
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    data = query.data
    current_path = context.user_data.get("current_path", QUIZ_DIRECTORY)

    if data.startswith("dir:"):
        dir_choice = data.split("dir:")[1]
        if dir_choice == "..":
            parent = os.path.dirname(current_path)
            if os.path.abspath(parent) == os.path.abspath(QUIZ_DIRECTORY):
                parent = QUIZ_DIRECTORY
            context.user_data["current_path"] = parent
        else:
            new_path = os.path.join(current_path, dir_choice)
            context.user_data["current_path"] = new_path

        await show_directory(chat_id, context, query)

    elif data.startswith("file:"):
        filename = data.split("file:")[1]
        file_path = os.path.join(current_path, filename)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                quiz_data = json.load(f)
            if not isinstance(quiz_data, list) or not all("question" in q and "options" in q and "answer" in q for q in quiz_data):
                await query.edit_message_text("Invalid quiz format in the file.")
                return

            filtered_quiz = [
                q for q in quiz_data 
                if len(q["question"]) < 300 and 
                all(len(opt) < 100 for opt in q["options"]) and 
                ((str(q["answer"]).isdigit() and 1 <= int(q["answer"]) <= len(q["options"])) or q["answer"] in q["options"])
            ]
            if not filtered_quiz:
                await query.edit_message_text("No valid questions found after filtering.")
                return

            user_data[query.from_user.id] = {
                "quiz": filtered_quiz,
                "index": 0,
                "correct": 0,
                "attempted": 0,
                "limit": len(filtered_quiz),
                "timer": False,
                "active_quiz": False,
                "poll_id": None,
                "chat_id": chat_id
            }
            total_questions = len(filtered_quiz)
            buttons = [
                [InlineKeyboardButton("Yes", callback_data="yeah")],
                [InlineKeyboardButton("No", callback_data="no")],
                [InlineKeyboardButton("⬅️", callback_data="pre_timer"),
                InlineKeyboardButton("🏠", callback_data="home")]
            ]
            reply_markup = InlineKeyboardMarkup(buttons)
            try:
                await query.edit_message_text("Would you like a timer for the quiz?", reply_markup=reply_markup)
            except Exception:
                await context.bot.send_message(chat_id, "Would you like a timer for the quiz?", reply_markup=reply_markup)


        except Exception as e:
            print(f"Error loading quiz: {traceback.format_exc()}")
            await query.edit_message_text("Error loading quiz. Try again later.")

async def limit_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles selection of question limit then asks for timer option or navigation commands."""
    query = update.callback_query
    user_id = query.from_user.id
    current_time = datetime.utcnow()

    # Prevent multiple taps within 2 seconds
    last_tap_time = context.user_data.get(f"last_tap_{user_id}")
    if last_tap_time and (current_time - last_tap_time).total_seconds() < 2:
        await query.answer("⏳ You need to tap once only", show_alert=False)
        return  # Ignore this tap

    context.user_data[f"last_tap_{user_id}"] = current_time
    
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    data = query.data

    if data == "limit_all":
        user_data[user_id]["limit"] = len(user_data[user_id]["quiz"])
        await ask_for_timer(chat_id, query, context)
    elif data == "limit_custom":
        await query.edit_message_text(
            f"How many questions you want to attempt (1 to {len(user_data[user_id]['quiz'])}).\nYou have only 5 tries."
        )
        context.user_data["awaiting_limit"] = True
    elif data == "pre_limit":
        await show_directory(chat_id, context, query)
    elif data == "home":
        context.user_data["current_path"] = QUIZ_DIRECTORY
        await show_directory(chat_id, context, query)

async def ask_for_timer(chat_id, query, context: ContextTypes.DEFAULT_TYPE):
    """Asks the user if they want a timer for the quiz."""
    buttons = [
        [InlineKeyboardButton("Yes", callback_data="yeah")],
        [InlineKeyboardButton("No", callback_data="no")],
        [InlineKeyboardButton("⬅️", callback_data="pre_timer"),
         InlineKeyboardButton("🏠", callback_data="home")]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    try:
        await query.edit_message_text("Would you like a timer for the quiz?", reply_markup=reply_markup)
    except Exception:
        await context.bot.send_message(chat_id, "Would you like a timer for the quiz?", reply_markup=reply_markup)


async def timer_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles timer selection and navigation commands from the timer inline keyboard."""
    query = update.callback_query
    user_id = query.from_user.id
    current_time = datetime.utcnow()

    # Prevent multiple taps within 2 seconds
    last_tap_time = context.user_data.get(f"last_tap_{user_id}")
    if last_tap_time and (current_time - last_tap_time).total_seconds() < 2:
        await query.answer("⏳ You need to tap once only", show_alert=False)
        return  # Ignore this tap
    
    
    context.user_data[f"last_tap_{user_id}"] = current_time
    
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    data = query.data

    if data == "yeah":
        user_data[user_id]["timer"] = True
        user_data[user_id]["active_quiz"] = True  
        await query.edit_message_text("Starting quiz now...")
        await send_quiz(chat_id, user_id, context)
    elif data == "no":
        user_data[user_id]["timer"] = False
        user_data[user_id]["active_quiz"] = True
        await query.edit_message_text("Starting quiz now...")
        await send_quiz(chat_id, user_id, context)
    elif data == "pre_timer":
        total_questions = len(user_data[user_id]["quiz"])
        buttons = [
            [InlineKeyboardButton(f"All ({total_questions})", callback_data="limit_all")],
            [InlineKeyboardButton("Custom", callback_data="limit_custom")],
            [InlineKeyboardButton("⬅️", callback_data="pre_limit"),
             InlineKeyboardButton("🏠", callback_data="home")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(
            f"The quiz has {total_questions} valid questions.\nDo you want to use all questions or set a custom number?",
            reply_markup=reply_markup
        )
    elif data == "home":
        context.user_data["current_path"] = QUIZ_DIRECTORY
        await show_directory(chat_id, context, query)

def calculate_quiz_timer(question):
    """
    Dynamically calculates the timer for a quiz question based on its length.
    
    :param question: A dictionary containing "question" text and "options" list.
    :return: An integer representing the timer in seconds.
    """
    base_time = 10  # Minimum time for any question
    max_time = 30   # Maximum allowed time

    question_length = len(question["question"])
    option_length = sum(len(opt) for opt in question["options"])

    # Calculate additional time: 1 second for every 20 characters
    extra_time = (question_length + option_length) // 20

    return min(base_time + extra_time, max_time)

async def send_quiz(chat_id, user_id, context: ContextTypes.DEFAULT_TYPE):
    """Sends the next quiz question and schedules a timeout job if timer is enabled."""
    try:
        user = user_data[user_id]

        if "shuffled" not in user:
            random.shuffle(user["quiz"])
            user["shuffled"] = True

        max_questions = min(user["limit"], len(user["quiz"]))

        if user["index"] < max_questions:
            question = user["quiz"][user["index"]]
            options = question["options"]

            correct_answer = question["answer"]
            if isinstance(correct_answer, str) and correct_answer.isdigit():
                if correct_answer in options:
                    None
                elif 1<=int(correct_answer)<=len(options):
                    correct_answer = options[int(correct_answer) - 1]
                else:
                    return
            elif isinstance(correct_answer, int) and 1 <= correct_answer <= len(options):
                correct_answer = options[correct_answer - 1]

             # Ensure 'None of the above' stays at the end if presents
            if any("None of the above".lower() in opt.lower() for opt in options):
                none_option = next(opt for opt in options if "None of the above".lower() in opt.lower())
                other_options = [opt for opt in options if opt != none_option]
                random.shuffle(other_options)
                options = other_options + [none_option]
                question["options"] = options
            
            else:
                random.shuffle(options)
            user["quiz"][user["index"]]["answer"]=correct_answer
            correct_option_id = options.index(correct_answer)

            quiz_timer = calculate_quiz_timer(question) if user.get("timer", False) else None

            msg = await context.bot.send_poll(
            chat_id,
            question=str(1+user["index"])+"."+question["question"],
            options=options,
            type=Poll.QUIZ,
            correct_option_id=correct_option_id,
            is_anonymous=False,
            open_period=quiz_timer
            )


            # Store poll details
            user_data[user_id]["poll_message_id"] = msg.message_id
            user["poll_id"] = msg.poll.id
            user["chat_id"] = chat_id
            user["unanswered_count"] = user.get("unanswered_count", 0) + 1

            # 🟢 Start the quiz timeout if timer is enabled
            if user.get("timer", False):
                context.job_queue.run_once(timeout_quiz, quiz_timer+2, chat_id=chat_id, name=f"quiz_{user_id}")

            if not user.get("timer", False):
                context.job_queue.run_once(check_inactivity, 120, chat_id=chat_id, name=f"inactive_{user_id}")

        else:
            user["active_quiz"] = False
            await show_leaderboard(chat_id, user_id, context)

    except Exception as e:
        print(f"Error in send_quiz: {traceback.format_exc()}")

async def handle_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles user answers to quiz polls and cancels the timeout job if answered."""
    
    try:
        poll_answer = update.poll_answer
        user_id = poll_answer.user.id

        if user_id in user_data:
            user = user_data[user_id]
            chat_id = user["chat_id"]
            max_questions = min(user["limit"], len(user["quiz"]))
            
            if user["index"] < max_questions:
                question = user["quiz"][user["index"]]

                correct_index = question["options"].index(question["answer"])
                user["attempted"] += 1

                # Reset unanswered count when a user answers
                user["unanswered_count"] = 0

                if context.job_queue:
                    current_jobs = context.job_queue.get_jobs_by_name(f"quiz_{user_id}")
                    for job in current_jobs:
                        job.schedule_removal()

                if not user.get("timer", False) and context.job_queue:
                    inactivity_jobs = context.job_queue.get_jobs_by_name(f"inactive_{user_id}")
                    for job in inactivity_jobs:
                        job.schedule_removal()

                if poll_answer.option_ids and poll_answer.option_ids[0] == correct_index:
                    user["correct"] += 1

                user["index"] += 1
                await send_quiz(chat_id, user_id, context)

    except Exception as e:
        print(f"Error in handle_poll: {traceback.format_exc()}")

async def check_inactivity(context: ContextTypes.DEFAULT_TYPE):
    """Cancels the quiz if a user is inactive for 2 minutes (only in no-timer mode)."""
    job = context.job
    chat_id = job.chat_id
    user_id = int(job.name.split("_")[-1])

    if user_id in user_data and user_data[user_id].get("active_quiz", False):
        await force_quit_quiz(chat_id, user_id, context)

async def force_quit_quiz(chat_id, user_id, context: ContextTypes.DEFAULT_TYPE):
    """Forcibly quits the quiz if the user reaches the unanswered limit or times out."""
    user = user_data.get(user_id, {})

    if user.get("active_quiz", False):
        attempted = user.get("attempted", 0)
        correct = user.get("correct", 0)
        wrong = attempted - correct  # Questions attempted but answered wrong

        # Mark the quiz as attempted even if the user quit
        update_user_stats(
            user_id,
            quiz_attempted=1,
            questions_attempted=attempted,
            right=correct,
            wrong=wrong
        )

        user["active_quiz"] = False
        del user_data[user_id]

        await context.bot.send_message(
            chat_id,
            "Quiz canceled due to inactivity. Your progress has been saved."
        )
async def timeout_quiz(context: ContextTypes.DEFAULT_TYPE):
    """Handles quiz timeout when a user doesn't respond in timer mode."""

    print("Hey")
    job = context.job
    chat_id = job.chat_id
    user_id = int(job.name.split("_")[-1])

    if user_id in user_data:
        user = user_data[user_id]
        max_questions = min(user["limit"], len(user["quiz"]))

        # Track the number of poll timeouts
        user["timeout_count"] = user.get("timeout_count", 0) + 1

        # 🔴 If 5 polls timed out, quit the quiz
        if user["timeout_count"] >= 5:
            await context.bot.send_message(chat_id, "⚠️ Quiz canceled due to 5 unanswered polls. Your progress has been saved.")
            await force_quit_quiz(chat_id, user_id, context)
            return

        # Otherwise, move to the next question
        if user["index"] < max_questions:
            user["index"] += 1
            await send_quiz(chat_id, user_id, context)
        else:
            user["active_quiz"] = False
            await show_leaderboard(chat_id, user_id, context)

async def show_leaderboard(chat_id, user_id, context: ContextTypes.DEFAULT_TYPE):
    """Displays the final quiz results and updates the aggregated stats in the database."""
    try:
        stats = user_data[user_id]
        message = (
            f"Quiz completed!\n"
            f"Attempted: {stats['attempted']}\n"
            f"Correct: {stats['correct']}\n"
            f"Wrong: {stats['attempted'] - stats['correct']}"
        )

        # Update database stats: each finished quiz counts as 1 quiz attempt.
        update_user_stats(
            user_id,
            quiz_attempted=1,
            questions_attempted=stats["attempted"],
            right=stats["correct"],
            wrong=stats["attempted"] - stats["correct"]
        )
        await context.bot.send_message(chat_id, message)
        context.user_data["active"] = False
    except Exception as e:
        print(f"Error in show_leaderboard: {traceback.format_exc()}") 

async def delete_incoming_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes the incoming message."""
    try:
        chat_id = update.message.chat_id
        message_id = update.message.message_id
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        print(f"Failed to delete message: {e}")

async def combined_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.text and not update.message.text.startswith("/"):
            correct = False
            user_id = update.message.from_user.id
            chat_id = update.message.chat_id

            if context.user_data.get("awaiting_limit", False):
                if "limit_attempts" not in context.user_data:
                    context.user_data["limit_attempts"] = 5
                try:
                    limit_val = int(update.message.text)
                    max_questions = len(user_data[user_id]["quiz"])
                    if 1 <= limit_val <= max_questions:
                        correct = True
                        user_data[user_id]["limit"] = limit_val
                        del context.user_data["awaiting_limit"]
                        context.user_data.pop("limit_attempts", None)
                        await update.message.reply_text(f"Question number set to {limit_val}.")
                        await ask_for_timer(chat_id, update.message, context)
                    else:
                        context.user_data["limit_attempts"] -= 1
                        attempts_left = context.user_data["limit_attempts"]
                        if attempts_left <= 0:
                            await update.message.reply_text("No attempts left. Canceling input.")
                            del context.user_data["awaiting_limit"]
                            context.user_data.pop("limit_attempts", None)
                            total_questions = len(user_data[user_id]["quiz"])
                            buttons = [
                                [InlineKeyboardButton(f"All ({total_questions})", callback_data="limit_all")],
                                [InlineKeyboardButton("Custom", callback_data="limit_custom")],
                                [InlineKeyboardButton("⬅️", callback_data="pre_limit"),
                                 InlineKeyboardButton("🏠", callback_data="home")]
                            ]
                            reply_markup = InlineKeyboardMarkup(buttons)
                            await update.message.reply_text(
                                f"The quiz has {total_questions} valid questions.\nDo you want to use all questions or set a custom number?",
                                reply_markup=reply_markup
                            )
                except ValueError:
                    context.user_data["limit_attempts"] -= 1
                    attempts_left = context.user_data["limit_attempts"]
                    if attempts_left <= 0:
                        await update.message.reply_text("No attempts left. Canceling input.")
                        del context.user_data["awaiting_limit"]
                        context.user_data.pop("limit_attempts", None)
                        total_questions = len(user_data[user_id]["quiz"])
                        buttons = [
                            [InlineKeyboardButton(f"All ({total_questions})", callback_data="limit_all")],
                            [InlineKeyboardButton("Custom", callback_data="limit_custom")],
                            [InlineKeyboardButton("⬅️", callback_data="pre_limit"),
                             InlineKeyboardButton("🏠", callback_data="home")]
                        ]
                        reply_markup = InlineKeyboardMarkup(buttons)
                        await update.message.reply_text(
                            f"The quiz has {total_questions} valid questions.\nDo you want to use all questions or set a custom number?",
                            reply_markup=reply_markup
                        )
            if not correct:
                None
                '''await context.bot.delete_message(
                    chat_id=update.message.chat_id, 
                    message_id=update.message.message_id
                )'''
        elif update.message.text.startswith("/"):
            '''await context.bot.delete_message(
                chat_id=update.message.chat_id, 
                message_id=update.message.message_id
            )'''
    except Exception as e:
        print(f"Error in combined_message_handler: {traceback.format_exc()}")

def main():
    TOKEN = "7886735286:AAEO7Br_jHiZkaqbrNtM7cShrDhTUh6UzEg"
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler(["start", "startx"], start))
    app.add_handler(CommandHandler("cancel", quit))
    app.add_handler(MessageHandler(filters.ALL, combined_message_handler))
    app.add_handler(CallbackQueryHandler(quiz_selection, pattern="^(dir:|file:)"))
    app.add_handler(CallbackQueryHandler(limit_selection, pattern="^(limit_all|limit_custom|pre_limit|home)$"))
    app.add_handler(CallbackQueryHandler(timer_selection, pattern="^(yeah|no|pre_timer|home)$"))
    app.add_handler(PollAnswerHandler(handle_poll))
    print("Bot started. Waiting for users...")
    app.run_polling()

if __name__ == "__main__":
    
    main()