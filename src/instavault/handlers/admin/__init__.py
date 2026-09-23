from aiogram import Router

from . import bot_status
from . import broadcast
from . import cache_stats
from . import dashboard
from . import manage_user
from . import user_control
from . import order_approvals

admin_router = Router(name="admin_master")

admin_router.include_router(dashboard.router)
admin_router.include_router(bot_status.router)
admin_router.include_router(broadcast.router)
admin_router.include_router(cache_stats.router)
admin_router.include_router(manage_user.router)
admin_router.include_router(user_control.router)
admin_router.include_router(order_approvals.router)
