from django.urls import path

from apps.core import api as core_api
from apps.core import views as core_views
from apps.deals import api as deals_api
from apps.deals.views import deal_export_csv
from apps.monitoring import api as monitoring_api
from apps.pricing import api as pricing_api

urlpatterns = [
    # Health (public)
    path("health/live/", core_views.health_live, name="health-live"),
    path("health/ready/", core_views.health_ready, name="health-ready"),
    # Identity
    path("auth/me/", core_api.AuthMeApi.as_view(), name="auth-me"),
    # Dashboard
    path("dashboard/stats/", core_api.DashboardStatsApi.as_view(), name="dashboard-stats"),
    # Search profiles
    path("search-profiles/", monitoring_api.SearchProfileListApi.as_view()),
    path("search-profiles/test/", monitoring_api.SearchProfileTestApi.as_view()),
    path("search-profiles/<uuid:pk>/", monitoring_api.SearchProfileDetailApi.as_view()),
    path("search-profiles/<uuid:pk>/run/", monitoring_api.SearchProfileRunApi.as_view()),
    # Pricing
    path("market-price-rules/", pricing_api.MarketRuleListApi.as_view()),
    path("market-price-rules/<uuid:pk>/", pricing_api.MarketRuleDetailApi.as_view()),
    path("defect-reserve-rules/", pricing_api.DefectRuleListApi.as_view()),
    path("defect-reserve-rules/<uuid:pk>/", pricing_api.DefectRuleDetailApi.as_view()),
    # Listings
    path("listings/", monitoring_api.ListingListApi.as_view()),
    path("listings/<uuid:pk>/", monitoring_api.ListingDetailApi.as_view()),
    path("listings/<uuid:pk>/status/", monitoring_api.ListingStatusApi.as_view()),
    path("listings/<uuid:pk>/reanalyze/", monitoring_api.ListingReanalyzeApi.as_view()),
    # Deals
    path("deals/", deals_api.DealListApi.as_view()),
    path("deals/export.csv", deal_export_csv, name="deals-export-csv"),
    path("deals/<uuid:pk>/", deals_api.DealDetailApi.as_view()),
    # Scan runs
    path("scan-runs/", monitoring_api.ScanRunListApi.as_view()),
    path("scan-runs/<uuid:pk>/", monitoring_api.ScanRunDetailApi.as_view()),
    path("scan-runs/<uuid:pk>/diagnostic/", monitoring_api.ScanRunDiagnosticApi.as_view()),
    # Settings / system
    path("settings/", core_api.SettingsApi.as_view(), name="api-settings"),
    path("system/status/", core_api.SystemStatusApi.as_view(), name="api-system-status"),
    path("system/pause/", core_api.SystemPauseApi.as_view(), name="api-system-pause"),
    path("system/resume/", core_api.SystemResumeApi.as_view(), name="api-system-resume"),
    path("system/cleanup/preview/", core_api.CleanupPreviewApi.as_view()),
    path("system/diagnostic/", core_api.SystemDiagnosticApi.as_view()),
    # Integrations
    path("integrations/telegram/test/", core_api.TelegramTestApi.as_view()),
    path("integrations/openai/check/", core_api.OpenAiCheckApi.as_view()),
]
