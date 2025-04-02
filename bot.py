import os
import json
import random
import traceback
import sqlite3
import aiohttp, logging
from telegram.error import TimedOut
from colorama import Fore, Style, init
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, PollAnswerHandler, MessageHandler,
    filters, ContextTypes, PollHandler
)
from datetime import datetime, timedelta
from collections import deque
logger = logging.getLogger("my_logger")
logger.setLevel(logging.INFO)

# Create a file handler for user logs
user_handler = logging.FileHandler("user_log.txt")
user_handler.setLevel(logging.INFO)
user_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
user_handler.setFormatter(user_formatter)
logger.addHandler(user_handler)

# Create a file handler for API usage logs
api_handler = logging.FileHandler("api_usage.log")
api_handler.setLevel(logging.INFO)
api_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
api_handler.setFormatter(api_formatter)
logger.addHandler(api_handler)

# Now, when you call logger.info() it will log to both files.
logger.info("This log message goes to both user_log.txt and api_usage.log")
def log_user_action(user_id, full_name, username, action, details=""):
    # Full timestamp for logging
    full_timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    # HMS timestamp for console output
    hms_timestamp = datetime.utcnow().strftime("%H:%M:%S")
    
    log_message = f"[{full_timestamp}] User: {full_name} (@{username}) ({user_id}) | Action: {action} | Details: {details}"
    
    # Log to file with full timestamp
    logging.info(log_message)

    # Define colors for different actions
    action_colors = {
        "started": Fore.GREEN,
        "answered": Fore.CYAN,
        "quit": Fore.RED,
        "inactive": Fore.YELLOW,
    }

    # Get color based on action keyword
    action_key = action.split()[0].lower()
    color = action_colors.get(action_key, Fore.WHITE)

    # Print with colors using HMS only
    print(f"{color}[{hms_timestamp}] 🔹 {full_name} (@{username}) {action} {details}{Style.RESET_ALL}")
# Track API calls per second
api_requests = deque(maxlen=30)

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

from collections import deque
import asyncio
MAX_REQUESTS_PER_SEC = 30  # Telegram API limit
semaphore = asyncio.Semaphore(MAX_REQUESTS_PER_SEC)
poll_queue = asyncio.Queue()

QUIZ_DIRECTORY = CONFIG["QUIZ_DIRECTORY"]
user_data = {}

# -------------------- DATABASE SETUP --------------------
import sqlite3

DB_PATH = "quiz_bot.db"

def init_db():
    """Initializes the SQLite database and creates necessary tables."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()

    # Table for tracking user quiz statistics
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT,
            total_quiz_attempted INTEGER DEFAULT 0,
            total_questions_attempted INTEGER DEFAULT 0,
            total_right INTEGER DEFAULT 0,
            total_wrong INTEGER DEFAULT 0,
            block_until DATETIME
        )
    ''')
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS completed_quizzes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        quiz_file TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quiz_attempts (
            user_id INTEGER,
            quiz_timestamp DATETIME
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT
        )
    ''')

    conn.commit()
    return conn

db_conn = init_db()

def mark_quiz_completed(user_id, quiz_file):
    conn = sqlite3.connect("quiz_bot.db")
    cursor = conn.cursor()

    cursor.execute("INSERT INTO completed_quizzes (user_id, quiz_file) VALUES (?, ?)", 
                   (user_id, quiz_file))
    
    conn.commit()
    conn.close()

def get_completed_quizzes(user_id):
    conn = sqlite3.connect("quiz_bot.db")
    cursor = conn.cursor()

    cursor.execute("SELECT quiz_file FROM completed_quizzes WHERE user_id = ?", (user_id,))
    completed_quizzes = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    return completed_quizzes

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

def has_reached_quiz_limit(user_id):
    """Checks if the user has reached their quiz limit in a 1-hour window."""
    now = datetime.utcnow()

    # Check if the user is already blocked
    user_stats = get_user_stats(user_id)
    if user_stats["block_until"]:
        block_until = datetime.strptime(user_stats["block_until"], "%Y-%m-%d %H:%M:%S")
        if now < block_until:
            return True  # User is still blocked

    one_hour_ago = now - timedelta(hours=1)
    quiz_limit = 4  # Regular users can take 4 quizzes per hour

    attempts = count_recent_attempts(user_id, one_hour_ago.strftime("%Y-%m-%d %H:%M:%S"))

    if attempts >= quiz_limit:
        block_until_time = now + timedelta(minutes=20)  # Block for 20 minutes
        set_user_block(user_id, block_until_time.strftime("%Y-%m-%d %H:%M:%S"))
        return True

    return False


def store_user_details(user_id, full_name, username):
    """Stores or updates user details in the database."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()

    # Check if the user already exists
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    existing_user = cursor.fetchone()

    if existing_user:
        # Update user details (if needed)
        cursor.execute("UPDATE users SET full_name = ?, username = ? WHERE user_id = ?",
                       (full_name, username, user_id))
    else:
        # Insert new user data
        cursor.execute("INSERT INTO users (user_id, full_name, username) VALUES (?, ?, ?)",
                       (user_id, full_name, username))

    conn.commit()
    conn.close()


# -------------------- TELEGRAM BOT FUNCTIONS --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = user.id
    chat_id = update.message.chat_id
    full_name = user.full_name  # Get full name
    username = user.username if user.username else "NoUsername"
    store_user_details(user_id, full_name, username)
    now = datetime.utcnow()
    if user_id not in user_data:
        user_data[user_id] = {}
        user_data[user_id]["active_menu"] = False
    active_users = sum(1 for u in user_data.values() if u.get("active_quiz", False))
    if active_users >= 5:
        await asyncio.sleep(5)

    print("Hello", user_data[user_id]["active_menu"])
    if user_id in user_data and user_data[user_id].get("active_menu", False):
        log_user_action(user_id, full_name, username, "is trying to restart the menu", f"in Chat ID: {update.message.chat_id}")
        #await update.message.reply_text("⚠️ You already have an active quiz. Finish it first before starting a new one.")
        return
    if user_id != CONFIG["ADMIN_USER_ID"]:
        user_stats = get_user_stats(user_id)
        
        # Check if user is blocked
        if user_stats["block_until"]:

            log_user_action(user_id, full_name, username, "is on waitlist still trying to start menu", f"in Chat ID: {update.message.chat_id}")
            block_until = datetime.strptime(user_stats["block_until"], "%Y-%m-%d %H:%M:%S")
            if now < block_until:
                return
        
        if has_reached_quiz_limit(user_id):
            await context.bot.send_message(chat_id, f"❌ You have reached your quiz limit. Please wait 20 Minutes....")
            return
    user_data[user_id]["active_menu"] = True
    log_user_action(user_id, full_name, username, "started menu", f"in Chat ID: {update.message.chat_id}")
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
    user = update.message.from_user
    user_id = user.id
    full_name = user.full_name

    username = user.username if user.username else "NoUsername"

    if user_id in user_data and user_data[user_id].get("active_quiz", False):
        chat_id = user_data[user_id].get("chat_id")
        poll_message_id = user_data[user_id].get("poll_message_id")
        if poll_message_id:
            try:
                await context.bot.stop_poll(chat_id=chat_id, message_id=poll_message_id)
                log_api_request("stop_poll")
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
        log_user_action(user_id, full_name, username, "Quit The Quiz", f"in Chat ID: {update.message.chat_id}")
        user_data[user_id]["active_quiz"] = False
        del user_data[user_id]
        if user_id in user_data:
            user_data[user_id]["active_menu"] = False

        
        await update.message.reply_text("Your active quiz has been canceled.You can start a new quiz with /start.")
        log_api_request("send_message")
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
    completed_quizzes = get_completed_quizzes(chat_id)
    remaining_files = [f for f in files if f not in completed_quizzes]
    buttons = []
    inline_items = []  # Temporary list to store buttons for 2×2 format

    # Add directories (📁 Folder Name)
    for d in dirs:
        dir_path = os.path.join(current_path, d)
        filelist = set()
        if contains_json(dir_path):
            for file in os.listdir(dir_path):
                file_path = os.path.relpath(os.path.join(dir_path, file), QUIZ_DIRECTORY)
                filelist.add(file_path)
            if filelist.issubset(set(completed_quizzes)):
                inline_items.append(InlineKeyboardButton(f"📁 {d} + ✅", callback_data=f"dir:{d}"))
            else:
                inline_items.append(InlineKeyboardButton(f"📁 {d}", callback_data=f"dir:{d}"))


    for f in files:
        relative_path = os.path.relpath(os.path.join(current_path, f), QUIZ_DIRECTORY)
        display_name = f"📝 {f[:-5]}"  # Remove .json extension
        if relative_path in completed_quizzes:
            display_name += " ✅"  # Mark completed quizzes
        print(current_path, relative_path)
        inline_items.append(InlineKeyboardButton(display_name, callback_data=f"file:{relative_path}"))

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
    
    log_api_request("send_message")

async def quiz_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles inline keyboard callbacks for directory navigation and file selection."""
    query = update.callback_query
    user_id = query.from_user.id
    current_time = datetime.utcnow()

    # Prevent multiple taps within 2 seconds
    last_tap_time = context.user_data.get(f"last_tap_{user_id}")
    if last_tap_time and (current_time - last_tap_time).total_seconds() < 2:
        #await query.answer("You need to tap once only", show_alert=False)
        return  # Ignore this tap

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
        log_api_request("edit_message_text")
        await show_directory(chat_id, context, query)

    elif data.startswith("file:"):
        filename = data.split("file:")[1]
        file_path = os.path.join(QUIZ_DIRECTORY, data[5:])
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
                "filename":filename,
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
                [InlineKeyboardButton("⏳ Yes", callback_data="yeah")],
                [InlineKeyboardButton("⏲️ No", callback_data="no")],
                [InlineKeyboardButton("⬅️", callback_data="pre_timer"),
                InlineKeyboardButton("🏠", callback_data="home")]
            ]
            reply_markup = InlineKeyboardMarkup(buttons)
            try:
                await query.edit_message_text("⏳ Do you want timer for the quiz?", reply_markup=reply_markup)
            except Exception:
                await context.bot.send_message(chat_id, "⏳ Do you want timer for the quiz?", reply_markup=reply_markup)


        except Exception as e:
            print(f"Error loading quiz: {traceback.format_exc()}")
            await query.edit_message_text("Error loading quiz. Try again later.")

async def ask_for_timer(chat_id, query, context: ContextTypes.DEFAULT_TYPE):
    """Asks the user if they want a timer for the quiz."""
    buttons = [
        [InlineKeyboardButton("⏳ Yes", callback_data="yeah")],
        [InlineKeyboardButton("⏲️ No", callback_data="no")],
        [InlineKeyboardButton("⬅️", callback_data="pre_timer"),
         InlineKeyboardButton("🏠", callback_data="home")]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    try:
        await query.edit_message_text("⏳ Do you want timer for the quiz?", reply_markup=reply_markup)
    except Exception:
        await context.bot.send_message(chat_id, "⏳ Do you want timer for the quiz?", reply_markup=reply_markup)


async def timer_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles timer selection and navigation commands from the timer inline keyboard."""
    query = update.callback_query
    user_id = query.from_user.id
    current_time = datetime.utcnow()

    # Prevent multiple taps within 2 seconds
    last_tap_time = context.user_data.get(f"last_tap_{user_id}")
    if last_tap_time and (current_time - last_tap_time).total_seconds() < 2:
        #await query.answer("⏳ You need to tap once only", show_alert=False)
        return  # Ignore this tap
    
    
    context.user_data[f"last_tap_{user_id}"] = current_time
    
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_id = user.id
    chat_id = query.message.chat_id
    data = query.data

    if data == "yeah" or data == "no":
        user_data[user_id]["timer"] = (data == "yeah")
        user_data[user_id]["active_quiz"] = True
        await query.edit_message_text("Starting quiz now...")
        now = datetime.utcnow()
        record_quiz_attempt(user_id, now.strftime("%Y-%m-%d %H:%M:%S"))

        full_name = user.full_name
        username = user.username if user.username else "NoUsername"
        log_user_action(user_id, full_name, username, "Started the Quiz", f"in Chat ID: {query.message.chat_id}")
        await staggered_quiz_start(chat_id, user_id, context)
    elif data == "pre_timer":
        await show_directory(chat_id, context, query)
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

import asyncio
def log_api_request(api_type):
    """Tracks API request timestamps and logs usage."""
    global api_requests

    # Get current time
    now = datetime.utcnow()

    # Append request timestamp
    api_requests.append(now)

    # Count API requests in the last second
    requests_last_second = sum(1 for t in api_requests if (now - t).total_seconds() < 1)

    # Log API request count
    logging.info(f"API Request: {api_type} | Requests in last second: {requests_last_second}")
    
    # Print in console (optional)
    print(f"📊 API Request: {api_type} | Requests/sec: {requests_last_second}")

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

            raw_explanation = question.get("source", "").strip()
            poll_kwargs = {}
            if raw_explanation not in ("Unknown", "NA", ""):
                poll_kwargs = {
                    "explanation": raw_explanation,
                    "explanation_parse_mode": 'HTML'
                }
            poll_time = calculate_quiz_timer(question) if user.get("timer", False) else None
            await asyncio.sleep(2)

            
            try:
                msg = await context.bot.send_poll(
                    chat_id,
                    question=str(1+user["index"])+"."+question["question"],
                    options=options,
                    type=Poll.QUIZ,
                    correct_option_id=correct_option_id,
                    is_anonymous=False,
                    open_period=poll_time,
                    **poll_kwargs
                )
            except TimedOut:
                print("Timeout occurred while sending poll. Retrying...")
                await asyncio.sleep(5)  # Short delay before retrying
                return await send_quiz(chat_id, user_id, context)
            log_api_request("send_poll")
            user_data[user_id]["poll_message_id"] = msg.message_id
            user["poll_id"] = msg.poll.id
            user["chat_id"] = chat_id
            user["unanswered_count"] = user.get("unanswered_count", 0) + 1

            # 🟢 Start the quiz timeout if timer is enabled
            if user.get("timer", False):
                context.job_queue.run_once(timeout_quiz, poll_time, chat_id=chat_id, name=f"quiz_{user_id}")

            if not user.get("timer", False):
                context.job_queue.run_once(check_inactivity, 10, chat_id=chat_id, name=f"inactive_{user_id}")

        else:
            user["active_quiz"] = False
            await show_leaderboard(chat_id, user_id, context)

    except Exception as e:
        print(f"Error in send_quiz: {traceback.format_exc()}")


import traceback

from telegram.error import TimedOut

async def handle_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles user answers to quiz polls and cancels the timeout job if answered."""

    try:
        poll_answer = update.poll_answer
        user = poll_answer.user
        user_id = user.id
        full_name = user.full_name

        username = user.username if user.username else "NoUsername"
        log_user_action(user_id, full_name, username, "Answered The Poll", f"in Chat ID: {user_id}")

        if user_id in user_data:
            user = user_data[user_id]
            chat_id = user["chat_id"]
            max_questions = min(user["limit"], len(user["quiz"]))

            if user["index"] < max_questions:
                question = user["quiz"][user["index"]]

                # Check if poll_answer.option_ids exists and is not empty
                if poll_answer.option_ids:
                    selected_option = poll_answer.option_ids[0]
                    correct_index = question["options"].index(question["answer"])

                    user["attempted"] += 1  # Track total attempts
                    user["timeout_count"] = 0  # Reset timeout count when answered

                    # ✅ Safely remove timeout job
                    try:
                        if context.job_queue:
                            for job in context.job_queue.get_jobs_by_name(f"quiz_{user_id}"):
                                job.schedule_removal()
                            for job in context.job_queue.get_jobs_by_name(f"inactive_{user_id}"):
                                job.schedule_removal()
                    except TimedOut:
                        print("Timeout while removing jobs. Continuing...")
                    if selected_option != correct_index:
                        if not user.get("retry_mode", False):
                            user.setdefault("wrong_questions", []).append(question)
                    else:
                        user["correct"] += 1  # Increase correct answer count
                # ✅ Move to the next question with error handling
                if user["index"] + 1 < max_questions:
                    user["index"] += 1
                    try:
                        await send_quiz(chat_id, user_id, context)
                    except TimedOut:
                        print("Timeout while sending next question. Retrying...")
                        await asyncio.sleep(2)
                        await send_quiz(chat_id, user_id, context)  # Retry!
                else:
                    user["active_quiz"] = False
                    try:
                        await show_leaderboard(chat_id, user_id, context)
                    except TimedOut:
                        print("Timeout in leaderboard. Retrying...")
                        await asyncio.sleep(2)
                        await show_leaderboard(chat_id, user_id, context)  # Retry!

    except TimedOut:
        print("Timeout occurred in handle_poll. Ignoring and continuing...")
    except Exception as e:
        print(f"Error in handle_poll: {traceback.format_exc()}")

async def check_inactivity(context: ContextTypes.DEFAULT_TYPE):
    """Cancels the quiz if a user is inactive for 2 minutes (only in no-timer mode)."""
    job = context.job
    chat_id = job.chat_id
    user_id = int(job.name.split("_")[-1])

    if user_id in user_data and user_data[user_id].get("active_quiz", False):
        full_name = user_data[user_id].get("full_name", "Unknown User")
        username = user.username if user.username else "NoUsername"
        
        log_user_action(user_id, full_name, username, "was inactive, quiz canceled", f"in Chat ID: {update.message.chat_id}")
        await force_quit_quiz(chat_id, user_id, context, message="inactive")
        
async def force_quit_quiz(chat_id, user_id, context: ContextTypes.DEFAULT_TYPE, message):
    """Forcibly quits the quiz if the user reaches the unanswered limit or times out."""
    user = user_data.get(user_id, {})

    print("force quit", context)
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
        full_name = user_data[user_id].get("full_name", "Unknown User")
        username = user.username if user.username else "NoUsername"
        log_user_action(user_id, full_name, username, "was inactive, quiz canceled", f"in Chat ID: {update.message.chat_id}")
        user["active_quiz"] = False
        del user_data[user_id]
        if message=="inactive":
            await context.bot.send_message(chat_id, "Quiz canceled due to inactivity. Select another quiz using /start")
        
async def timeout_quiz(context: ContextTypes.DEFAULT_TYPE):
    """Handles quiz timeout when a user doesn't respond in timer mode."""

    print("timeout")
    job = context.job
    chat_id = job.chat_id
    user_id = int(job.name.split("_")[-1])

    if user_id in user_data:
        user = user_data[user_id]
        max_questions = min(user["limit"], len(user["quiz"]))

        # Track the number of poll timeouts
        user["timeout_count"] = user.get("timeout_count", 0) + 1

        # 🔴 If 5 polls timed out, quit the quiz
        if user["timeout_count"] >=4:
            await context.bot.send_message(chat_id, "⚠️ Quiz canceled due to inactivity. Select another quiz using /start")
            await force_quit_quiz(chat_id, user_id, context, message="unattempt")
            return

        # Otherwise, move to the next question
        if user["index"] < max_questions:
            user["index"] += 1
            await send_quiz(chat_id, user_id, context)
        else:
            user["active_quiz"] = False
            await show_leaderboard(chat_id, user_id, context)


from telegram.error import TimedOut


async def show_leaderboard(chat_id, user_id, context: ContextTypes.DEFAULT_TYPE):
    """Displays the final quiz results and updates the database."""
    try:
        stats = user_data[user_id]
        filename = stats["filename"]

        message = (
            "🏆 Quiz Completed!\n\n"
            "📊 Your Performance Summary:\n"
            "────────────────────────────\n"
            f"📝 Questions Attempted: {stats['attempted']}\n"
            f"✅ Correct Answers:     {stats['correct']}\n"
            f"❌ Incorrect Answers:   {stats['attempted'] - stats['correct']}\n"
            "────────────────────────────\n"
            "🎉 Thank you for participating!\n"
        )


        # ✅ Update user stats in the database
        update_user_stats(
            user_id,
            quiz_attempted=1,
            questions_attempted=stats["attempted"],
            right=stats["correct"],
            wrong=stats["attempted"] - stats["correct"]
        )

        # ✅ Mark quiz as completed
        if "completed_quizzes" not in context.user_data:
            context.user_data["completed_quizzes"] = []
        if filename not in context.user_data["completed_quizzes"]:
            context.user_data["completed_quizzes"].append(filename)

        if user_id in user_data:
            user_data[user_id]["active_menu"] = True

        mark_quiz_completed(user_id, filename)

        inline = []
        wrong_questions = stats.get("wrong_questions", [])
        wrong_count = len(wrong_questions)

        print(wrong_count)
        if stats.get("retry_mode", False):
            reply_markup = InlineKeyboardMarkup(inline)
            try:
                 await context.bot.send_message(chat_id, message, reply_markup=reply_markup)
            except TimedOut:
                print("Timeout while sending leaderboard. Retrying...")
                await asyncio.sleep(2)
                await context.bot.send_message(chat_id, message, reply_markup=reply_markup)
            return
        if wrong_count > 0:
            message += f"\n\nYou have {wrong_count} wrong question(s). Would you like to reattempt them?"
            inline.append([
                InlineKeyboardButton("Yes, Retry", callback_data="retry_choice:yes"),
                InlineKeyboardButton("No", callback_data="retry_choice:no")
            ])
                    # ✅ Send results message with timeout handling
            try:
                reply_markup = InlineKeyboardMarkup(inline)
                await context.bot.send_message(chat_id, message, reply_markup=reply_markup)
            except TimedOut:
                print("Timeout while sending leaderboard. Retrying...")
                await asyncio.sleep(2)
                await context.bot.send_message(chat_id, message, reply_markup=reply_markup)
        else:
            # ✅ Check quiz limit & handle timeout
            if has_reached_quiz_limit(user_id) and user_id != CONFIG["ADMIN_USER_ID"]:
                try:
                    await context.bot.send_message(
                        chat_id,
                        f"❌ You have reached your quiz limit. Try after 20 minutes...."
                    )
                except TimedOut:
                    print("Timeout while sending limit message. Retrying...")
                    await asyncio.sleep(2)
                    await context.bot.send_message(
                        chat_id,
                        f"❌ You have reached your quiz limit. Try after 20 minutes...."
                    )
                if user_id in user_data:
                    user_data[user_id]["active_menu"] = True

                return

            # ✅ Show updated quiz directory with timeout handling
            try:
                await asyncio.sleep(2)

                await show_directory(chat_id, context)
            except TimedOut:
                print("Timeout while showing directory. Retrying...")
                await asyncio.sleep(2)
                await show_directory(chat_id, context)  # Retry
        
                user_data[user_id]["active_menu"] = True

    except TimedOut:
        print("Timeout occurred in show_leaderboard. Ignoring and continuing...")
    except Exception as e:
        print(f"Error in show_leaderboard: {traceback.format_exc()}")


async def retry_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the inline callback when a user is asked whether they want to reattempt
    their wrong questions. Expected callback data is either "retry_choice:yes" or "retry_choice:no".
    """
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_id = user.id
    chat_id = query.message.chat_id

    # Expecting callback data in the format "retry_choice:yes" or "retry_choice:no"
    choice = query.data.split(":")[1].strip().lower()

    if choice == "yes":
        # Check if there are wrong questions available to retry.
        if user_id not in user_data or not user_data[user_id].get("wrong_questions"):
            await query.edit_message_text("No wrong questions to retry. Great job!")
            return

        session = user_data[user_id]
        wrong_questions = session.get("wrong_questions", [])
        if not wrong_questions:
            await query.edit_message_text("No wrong questions to retry. Great job!")
            return

        # Mark that this session is a retry so that further wrong answers won't be recorded.
        session["retry_mode"] = True

        # Reset the session with only the wrong questions.
        session["quiz"] = wrong_questions.copy()
        session["index"] = 0
        session["attempted"] = 0
        session["correct"] = 0
        session["limit"] = len(wrong_questions)
        session["active_quiz"] = True

        # Clear wrong_questions to give only one retry chance.
        session["wrong_questions"] = []

        await query.edit_message_text("Starting a new quiz with your incorrectly answered questions!")
        await send_quiz(chat_id, user_id, context)

    elif choice == "no":
        # User chose not to retry. Now, enforce quiz limit before navigating back.
        if has_reached_quiz_limit(user_id) and user_id != CONFIG["ADMIN_USER_ID"]:
            try:
                await context.bot.send_message(
                    chat_id,
                    "❌ You have reached your quiz limit. Try after 20 minutes...."
                )
            except TimedOut:
                print("Timeout while sending limit message. Retrying...")
                await asyncio.sleep(2)
                await context.bot.send_message(
                    chat_id,
                    "❌ You have reached your quiz limit. Try after 20 minutes...."
                )
        else:
            await query.edit_message_text("Okay, returning to quiz directory.")
            await show_directory(chat_id, context, query=None)


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

async def rate_limited_api_call(api_function, *args, **kwargs):
    """Ensures API calls stay within Telegram's 30 requests/sec limit."""
    async with semaphore:
        await asyncio.sleep(1 / MAX_REQUESTS_PER_SEC)  # Spread calls evenly
        return await api_function(*args, **kwargs)

async def staggered_quiz_start(chat_id, user_id, context):
    """Staggers quiz start times to prevent API overload."""
    delay = random.uniform(0, 3)  # Random delay between 0-3 sec
    await asyncio.sleep(delay)
    await enqueue_poll(chat_id, user_id, context)

async def poll_worker():
    """Processes queued poll requests at a controlled rate."""
    while True:
        chat_id, user_id, context = await poll_queue.get()
        await rate_limited_api_call(send_quiz, chat_id, user_id, context)
        await asyncio.sleep(1 / MAX_REQUESTS_PER_SEC)

async def enqueue_poll(chat_id, user_id, context):
    """Adds poll requests to the queue for controlled processing."""
    await poll_queue.put((chat_id, user_id, context))
async def cleanup_inactive_users(context: ContextTypes.DEFAULT_TYPE):
    """Removes users who haven't responded for MAX_TIMEOUTS questions, marks quiz as attempted, and updates the database."""

    MAX_TIMEOUTS = 4  # Ensure consistency with timeout_quiz()

    for user_id in list(user_data.keys()):
        user = user_data.get(user_id)  # Get user safely

        if user and user.get("timeout_count", 0) >= MAX_TIMEOUTS:
            chat_id = user["chat_id"]
            attempted = user.get("attempted", 0)
            correct = user.get("correct", 0)
            wrong = attempted - correct  # Questions attempted but answered wrong

            # ✅ Mark the quiz as attempted
            update_user_stats(
                user_id,
                quiz_attempted=1,
                questions_attempted=attempted,
                right=correct,
                wrong=wrong
            )

            # ✅ Send a message to the user
            try:
                await context.bot.send_message(chat_id, "❌ Your quiz was stopped due to inactivity.")
            except Exception as e:
                print(f"⚠️ Failed to send inactivity message to {user_id}: {e}")

            # ✅ Remove user data safely
            if user_id in user_data:
                del user_data[user_id]
                print(f"✅ Removed inactive user: {user_id}")
import sqlite3

def get_all_user_ids():
    """Fetch all user_ids from the user_stats table in the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM user_stats")
    results = cursor.fetchall()
    conn.close()
    return [row[0] for row in results]


async def announce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows the admin to broadcast an announcement to all users or a specific user."""
    user = update.message.from_user

    # Check if the sender is the admin.
    if user.id != CONFIG["ADMIN_USER_ID"]:
        await update.message.reply_text("❌ You are not authorized to make announcements.")
        return

    # Ensure arguments are provided
    if not context.args:
        await update.message.reply_text("Usage: /announce [user_id (optional)] <message>")
        return

    # Check if the first argument is a user ID
    first_arg = context.args[0]
    if first_arg.isdigit():
        user_id = int(first_arg)
        announcement_text = "📢:\n\n" + " ".join(context.args[1:])
        recipients = [user_id]
    else:
        announcement_text = "📢:\n\n" + " ".join(context.args)
        recipients = get_all_user_ids()  # Fetch all user IDs from the database

    unsuccessful = []
    for uid in recipients:
        try:
            await context.bot.send_message(uid, announcement_text)
        except Exception as e:
            print(f"Failed to send announcement to user {uid}: {e}")
            unsuccessful.append(uid)

    log_api_request("announce")
    
    if len(recipients) == 1:
        response = f"✅ Announcement sent to user {recipients[0]}."
    else:
        response = "✅ Announcement broadcasted successfully."

    if unsuccessful:
        response += f"\nFailed to send to: {unsuccessful}"

    await update.message.reply_text(response)


def main():
    TOKEN = "7886735286:AAEO7Br_jHiZkaqbrNtM7cShrDhTUh6UzEg"
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler(["start", "startx"], start))
    app.add_handler(CommandHandler("cancel", quit))
    app.add_handler(CommandHandler("announcex", announce))

    app.add_handler(MessageHandler(filters.ALL, combined_message_handler))
    app.add_handler(CallbackQueryHandler(quiz_selection, pattern="^(dir:|file:)"))
    app.add_handler(CallbackQueryHandler(timer_selection, pattern="^(yeah|no|pre_timer|home|next|buy_premium|return_pre)$"))
    app.add_handler(PollAnswerHandler(handle_poll))
    app.add_handler(CallbackQueryHandler(retry_choice_callback, pattern="^retry_choice:"))
    print("Bot started. Waiting for users...")
    loop = asyncio.get_event_loop()
    loop.create_task(poll_worker())
    app.job_queue.run_repeating(cleanup_inactive_users, interval=30, first=30)
    app.run_polling()

if __name__ == "__main__":
    
    main()
