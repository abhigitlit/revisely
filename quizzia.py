import discord
from discord.ext import commands, tasks
import aiohttp
import os, asyncio
import random
import html
from dotenv import load_dotenv

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

load_dotenv()

# Retrieve the Discord token from the environment
DISCO = os.getenv("DISCO")
if not DISCO:
    raise ValueError("No Discord token found. Please set DISCORD_TOKEN in your .env file.")


bot = commands.Bot(command_prefix="/", intents=intents)

# Store ongoing quiz sessions separately by channel (DM or server)
sessions = {}

class QuizSession:
    def __init__(self, channel, max_questions):
        self.channel = channel
        self.current_answer = None
        self.score = {}  # {user_id: points}
        self.question_count = 0
        self.active = True
        self.questions = []
        self.token = None   # Each session gets its own OpenTDB token.
        self.unanswered_streak = 0  # Count consecutive unanswered questions
        self.max_questions = max_questions

    async def get_token(self, session):
        async with session.get("https://opentdb.com/api_token.php?command=request") as token_resp:
            token_data = await token_resp.json()
            return token_data["token"]

    async def fetch_questions(self):
        async with aiohttp.ClientSession() as session:
            # Request a new token if none is set for this session
            if not self.token:
                self.token = await self.get_token(session)
            async with session.get(
                f"https://opentdb.com/api.php?amount=20&difficulty=easy&type=multiple&token={self.token}"
            ) as resp:
                data = await resp.json()
            # If token issues arise (expired or exhausted), get a new one and try again.
            if data["response_code"] in [3, 4]:
                self.token = await self.get_token(session)
                return await self.fetch_questions()
            self.questions.extend(data["results"])

    async def ask_question(self):
        qdata = self.questions.pop(0)
        question = html.unescape(qdata["question"])
        correct = html.unescape(qdata["correct_answer"])
        options = [correct] + [html.unescape(opt) for opt in qdata["incorrect_answers"]]
        random.shuffle(options)
        correct_index = options.index(correct) + 1  # 1-based index
        self.current_answer = str(correct_index)  # e.g., '1', '2', '3', or '4'
        msg = (
            f"📚 **Category:** *{qdata['category']}*\n\n"
            f"❓ **Q{self.question_count + 1}:** **{question}**\n"
            f"1️⃣ {options[0]}\n"
            f"2️⃣ {options[1]}\n"
            f"3️⃣ {options[2]}\n"
            f"4️⃣ {options[3]}\n"
        )
        await self.channel.send(msg)
    async def wait_for_answer(self):
        def check(m):
            return (
                m.channel == self.channel and
                m.content.strip() in ['1', '2', '3', '4']
            )

        while True:
            try:
                msg = await bot.wait_for("message", check=check, timeout=30)
            except asyncio.TimeoutError:
                await self.channel.send(f"⏱️ Time's up! The correct answer was: **{self.current_answer}**")
                break

            user = msg.author
            is_correct = msg.content.strip() == self.current_answer
            is_dm = msg.guild is None

            if is_correct:
                self.score[user.id] = self.score.get(user.id, 0) + 1
                await self.channel.send(f"✅ {user.mention} got it right! +1 point")
                break  # Only break loop if answer is correct

            elif is_dm:
                await self.channel.send(f"❌ {user.mention}, wrong answer! The correct option was: {self.current_answer}")
                break  # In DM, we allow one attempt only

            # In a server and wrong? Just ignore and wait again


    async def start(self):
        await self.fetch_questions()
        while self.active and self.question_count < self.max_questions:
            if self.unanswered_streak >= 10:
                await self.channel.send("❌ No answers received for 10 consecutive questions. Ending session.")
                break

            if not self.questions:
                await self.fetch_questions()

            await self.ask_question()
            self.question_count += 1

            try:
                answered = await asyncio.wait_for(self.wait_for_answer(), timeout=30)
                if answered:
                    self.unanswered_streak = 0
                else:
                    self.unanswered_streak += 1
            except asyncio.TimeoutError:
                await self.channel.send(f"⏱️ Time's up! The correct answer was: **{self.current_answer}**")
                self.unanswered_streak += 1

            await asyncio.sleep(3)
        await self.end()

    async def end(self):
        self.active = False
        sessions.pop(self.channel.id, None)
        if self.score:
            leaderboard = sorted(self.score.items(), key=lambda x: x[1], reverse=True)
            msg = "🏆 **Final Scores:**\n"
            for uid, points in leaderboard:
                user = await bot.fetch_user(uid)
                msg += f"🥇 {user.name}: **{points}** point(s)\n"
        else:
            msg = "😕 No correct answers were given."
        await self.channel.send(msg)

@bot.command(name="quiz")
async def quiz(ctx, command: str = None, limit: int = None):
    # Show usage when no subcommand is provided.
    if command is None:
        usage_msg = (
            "ℹ️ **Usage:**\n"
            "`/quiz start {x}` - Start a quiz with x questions (x must be between 10 and 50).\n"
            "`/quiz stop` - Stop the current quiz.\n"
            "`/quiz score` - Show the current scores."
        )
        await ctx.send(usage_msg)
        return

    if command.lower() == "start":
        if limit is None or limit < 10 or limit > 50:
            await ctx.send("❗ Please provide a valid quiz limit between 10 and 50. Example: `/quiz start 20`")
            return
        if ctx.channel.id in sessions:
            await ctx.send("⚠️ A quiz is already running in this channel!")
            return
        await ctx.send(
            f"🎮 **Starting quiz with {limit} questions!** Answer within 30s...\n💬 *Type the number of your answer (1, 2, 3, or 4)!*"
        )
        session = QuizSession(ctx.channel, max_questions=limit)
        sessions[ctx.channel.id] = session
        await session.start()

    elif command.lower() == "stop":
        session = sessions.get(ctx.channel.id)
        if session:
            session.active = False
            await ctx.send("🛑 **Quiz manually stopped.**")
        else:
            await ctx.send("❌ No quiz running in this channel.")

    elif command.lower() == "score":
        session = sessions.get(ctx.channel.id)
        if session and session.score:
            msg = "📊 **Current Scores:**\n"
            for uid, points in session.score.items():
                user = await bot.fetch_user(uid)
                msg += f"• {user.name}: **{points}** point(s)\n"
            await ctx.send(msg)
        else:
            await ctx.send("ℹ️ No scores yet or no quiz active.")
    else:
        await ctx.send("ℹ️ Use `/quiz start`, `/quiz stop`, or `/quiz score`.")

bot.run(DISCO)