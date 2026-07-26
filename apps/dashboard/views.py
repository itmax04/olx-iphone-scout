"""Dashboard view."""

from django.views.generic import TemplateView

from apps.core.permissions import AdministratorRequiredMixin
from apps.dashboard import selectors


class DashboardView(AdministratorRequiredMixin, TemplateView):
    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            context["stats"] = selectors.dashboard_stats("today")
            context["recent_candidates"] = selectors.recent_candidates()
            context["recent_errors"] = selectors.recent_errors()
            context["overdue_profiles"] = selectors.overdue_profiles()
            context["funnel"] = selectors.funnel()
            context["ai_month_cost"] = selectors.ai_month_cost()
            context["stats_error"] = None
        except Exception:
            context["stats_error"] = "Не удалось обновить блок статистики."
        return context
