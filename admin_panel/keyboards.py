"""
admin_panel/keyboards.py
~~~~~~~~~~~~~~~~~~~~~~~~
Inline keyboards for the Advanced Admin Panel.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def admin_dashboard_keyboard() -> InlineKeyboardMarkup:
    """Main keyboard for the Admin Panel."""
    keyboard = [
        [
            InlineKeyboardButton(text="👥 Total Users", callback_data="admin_users_count"),
            InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast"),
        ],
        [
            InlineKeyboardButton(text="🆕 New Accounts Today", callback_data="admin_new_accounts_today"),
            InlineKeyboardButton(text="⚡ Today Active Users", callback_data="admin_dau_today"),
        ],
        [
            InlineKeyboardButton(text="🔍 Manage User (Ban/Edit)", callback_data="admin_manage_user"),
        ],
        [
            InlineKeyboardButton(text="🔙 Back to Bot", callback_data="nav_dashboard")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def admin_back_keyboard() -> InlineKeyboardMarkup:
    """Keyboard with a single 'Back to Admin Panel' button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔙 Back to Admin Panel", callback_data="admin_dashboard")
            ]
        ]
    )


def broadcast_menu_keyboard() -> InlineKeyboardMarkup:
    """Sub-Menu keyboard for Broadcast Mode selection."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📢 All Users Broadcast", callback_data="broadcast_mode_all"),
            ],
            [
                InlineKeyboardButton(text="👤 Single User Broadcast", callback_data="broadcast_mode_single"),
            ],
            [
                InlineKeyboardButton(text="⏰ Scheduled Cron Broadcast", callback_data="broadcast_mode_cron"),
            ],
            [
                InlineKeyboardButton(text="🔙 Back to Admin Panel", callback_data="admin_dashboard"),
            ],
        ]
    )


def single_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard for Single User Broadcast Confirmation."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🚀 Send Direct Message", callback_data="confirm_single_broadcast"),
            ],
            [
                InlineKeyboardButton(text="❌ Cancel Broadcast", callback_data="cancel_single_broadcast"),
            ],
        ]
    )
