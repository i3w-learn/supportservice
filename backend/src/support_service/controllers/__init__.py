"""controllers — HTTP endpoints. See §3 of support-system-design.md."""

from support_service.controllers.admin_controller import attachment_router
from support_service.controllers.admin_controller import router as admin_router
from support_service.controllers.jobs_controller import router as jobs_router
from support_service.controllers.webhook_controller import router as webhook_router

__all__ = ["admin_router", "attachment_router", "jobs_router", "webhook_router"]
