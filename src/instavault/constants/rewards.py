# Economy
WELCOME_BONUS = 300
DAILY_MISSION_REWARD = 400
AD_WATCH_REWARD = 150
SHORTENER_TASK_REWARD = 500
SHORTENER_TOKEN_TTL = 1800  # 30 minutes
QUIZ_REWARD = 250
QUIZ_TOKEN_TTL = 1800  # 30 minutes
MYSTERY_BOX_MIN = 25
MYSTERY_BOX_MAX = 2000
SPARK_EXPIRY_DAYS = 90

# Packages (Moved to config/packages.py)

# Limits & VIPs
VIP_SLOTS = 1000

# Delivery & Compensation
DELIVERY_PROMISE_MINUTES = 45
COMPENSATION_TRIGGER_MINUTES = 60
COMPENSATION_AMOUNT = 200

# Referral
REFERRAL_JOIN_BONUS = 500
REFERRAL_MISSION_BONUS = 300
REFEREE_BONUS = 400
PASSIVE_PERCENT = 5
PASSIVE_MONTHLY_CAP = 500

# Time
TIMEZONE = "Asia/Kolkata"

# Runtime cache
BOT_USERNAME: str = ""
"""
config/packages.py
~~~~~~~~~~~~~~~~~~
Centralized configuration for all SMM packages.
Using Service ID-Driven Architecture.
"""

PACKAGES = {
    "starter": {
        "ui_name": "🌱 Starter Boost — 1,000 Views",
        "smm_service_id": 1052,
        "cost": 500,
        "views": 1000,
    },
    "growth": {
        "ui_name": "🔥 Growth Pack — 3,000 Views ⭐ BEST",
        "smm_service_id": 2108,
        "cost": 1200,
        "views": 3000,
    },
    "pro": {
        "ui_name": "💎 Pro Blast — 7,000 Views",
        "smm_service_id": 3050,
        "cost": 2500,
        "views": 7000,
    },
    "mega": {
        "ui_name": "⚡ Mega — 15,000 Views",
        "smm_service_id": 4012,
        "cost": 5000,
        "views": 15000,
    },
}
