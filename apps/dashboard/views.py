from apps.core.permissions import AdministratorRequiredMixin
from django.views.generic import TemplateView


class DashboardView(AdministratorRequiredMixin, TemplateView):
    template_name = "dashboard/index.html"
