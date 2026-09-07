import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Core Secrets (Strictly required, will crash if missing)
    BOT_TOKEN: str
    REDIS_URL: str

    # Optional / with defaults
    APK_FILE_ID: str = ""
    ADMIN_IDS: str = ""
    ADMIN_GROUP_ID: int = 0

    # SMM Panel
    SMM_API_URL: str = ""
    SMM_API_KEY: str = ""

    # GPLinks Shortener (Mission System)
    GPLINKS_API_URL: str = ""
    GPLINKS_API_KEY: str = ""

    # Webhook & Server
    REPLIT_DEV_DOMAIN: Optional[str] = None
    WEBHOOK_URL: Optional[str] = None
    BOT_PORT: int = 8099
    PORT: Optional[int] = None

    # Firebase
    FIREBASE_CREDENTIALS_PATH: str = "firebase_credentials.json"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# Initialize the settings engine (Fail-Fast happens right here!)
settings = Settings()

# ---------------------------------------------------------
# Drop-in Replacements (100% backward compatibility)
# ---------------------------------------------------------

BOT_TOKEN = settings.BOT_TOKEN
APK_FILE_ID = settings.APK_FILE_ID
ADMIN_IDS = [
    int(x.strip()) for x in settings.ADMIN_IDS.split(",") if x.strip().isdigit()
]
ADMIN_GROUP_ID = settings.ADMIN_GROUP_ID
SMM_API_URL = settings.SMM_API_URL
SMM_API_KEY = settings.SMM_API_KEY
GPLINKS_API_URL = settings.GPLINKS_API_URL
GPLINKS_API_KEY = settings.GPLINKS_API_KEY

REDIS_URL = settings.REDIS_URL

_replit_domain = settings.REPLIT_DEV_DOMAIN
WEBHOOK_URL = settings.WEBHOOK_URL or (
    f"https://{_replit_domain}" if _replit_domain else None
)

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = settings.PORT if settings.PORT is not None else settings.BOT_PORT

FIREBASE_CREDENTIALS_PATH = settings.FIREBASE_CREDENTIALS_PATH
if FIREBASE_CREDENTIALS_PATH == "firebase_credentials.json":
    FIREBASE_CREDENTIALS_PATH = os.path.join(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ),
        "firebase_credentials.json",
    )
