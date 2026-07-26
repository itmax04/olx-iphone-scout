"""Template context: version info and the monitoring status banner."""

from django.conf import settings
from django.http import HttpRequest

from apps.core.permissions import is_administrator


def app_context(request: HttpRequest) -> dict[str, object]:
    context: dict[str, object] = {
        "APP_VERSION": settings.APP_VERSION,
        "APP_ENV": settings.APP_ENV,
    }
    if is_administrator(getattr(request, "user", None)):
        try:
            from apps.core.services import effective_monitoring, get_app_state, worker_status

            state = get_app_state()
            context["app_state"] = state
            context["monitoring_effective"] = effective_monitoring(state)
            context["monitor_env_enabled"] = settings.MONITOR_ENABLED
            context["worker_status"] = worker_status(state)
        except Exception:
            # The banner must never take down a page (e.g. DB hiccup).
            context["app_state"] = None
            context["monitoring_effective"] = False
            context["monitor_env_enabled"] = settings.MONITOR_ENABLED
            context["worker_status"] = "UNAVAILABLE"
    return context
