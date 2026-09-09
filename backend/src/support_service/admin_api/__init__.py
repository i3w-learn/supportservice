"""admin_api — see §3 of support-system-design.md."""

from support_service.admin_api.routes import router as admin_router

__all__ = ["admin_router"]
