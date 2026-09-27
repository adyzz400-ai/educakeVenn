import os

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

EDUCAKE_LOGIN_URL = "https://my.educake.co.uk/login"

BOT_NAME = "VoboAi"
BOT_VERSION = "4.0.0"

MAX_CONCURRENT_JOBS = int(
    os.getenv("MAX_CONCURRENT_JOBS", "2")
)

SESSION_SECRET = os.getenv("SESSION_SECRET", "")

if not DISCORD_TOKEN:
    print("WARNING: DISCORD_TOKEN is missing.")

if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY is missing.")

if not SESSION_SECRET:
    print("WARNING: SESSION_SECRET is missing.")
