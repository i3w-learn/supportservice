"""controllers — HTTP endpoints. See §3 of support-system-design.md."""

from support_service.controllers.admin_controller import attachment_router, contact_router
from support_service.controllers.admin_controller import router as admin_router
from support_service.controllers.auth_controller import router as auth_router
from support_service.controllers.tasks_controller import router as tasks_router
from support_service.controllers.webhook_controller import router as webhook_router

__all__ = [
    "admin_router",
    "attachment_router",
    "auth_router",
    "contact_router",
    "tasks_router",
    "webhook_router",
]
