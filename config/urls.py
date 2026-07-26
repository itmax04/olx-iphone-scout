"""Root URL configuration."""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="dashboard:index", permanent=False)),
    path("accounts/", include("apps.core.account_urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("searches/", include("apps.monitoring.search_urls")),
    path("listings/", include("apps.monitoring.listing_urls")),
    path("runs/", include("apps.monitoring.run_urls")),
    path("prices/", include("apps.pricing.urls")),
    path("deals/", include("apps.deals.urls")),
    path("settings/", include("apps.core.settings_urls")),
    path("system/", include("apps.core.system_urls")),
    path("api/v1/", include("apps.core.api_urls")),
    path("admin/", admin.site.urls),
]

handler403 = "apps.core.views.permission_denied_view"
handler404 = "apps.core.views.page_not_found_view"
handler500 = "apps.core.views.server_error_view"
