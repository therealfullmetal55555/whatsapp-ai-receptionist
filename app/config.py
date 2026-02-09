import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
MY_WHATSAPP_NUMBER = os.getenv("MY_WHATSAPP_NUMBER", "")

# OpenAI / GPT-6 Sol
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")

# Google Calendar
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "")

# App
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8002"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Tallinn")
CLIENT_TIMEZONE = os.getenv("CLIENT_TIMEZONE", "Europe/Tallinn")

# Business
BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Wellness Studio Tallinn")
BUSINESS_HOURS_START = os.getenv("BUSINESS_HOURS_START", "09:00")
BUSINESS_HOURS_END = os.getenv("BUSINESS_HOURS_END", "18:00")
SLOT_DURATION = int(os.getenv("SLOT_DURATION_MINUTES", "60"))

# Mock flags
USE_MOCK_CALENDAR = not bool(GOOGLE_CALENDAR_ID and GOOGLE_CREDENTIALS_PATH)
USE_MOCK_LLM = not bool(OPENAI_API_KEY)
USE_MOCK_TWILIO = not bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN)

# For demo transcripts
DEMO_TRANSCRIPTS_PATH = BASE_DIR / "demo" / "conversation-transcripts.md"
