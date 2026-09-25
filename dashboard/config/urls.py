from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("v1/", include("ledger.urls")),
    path("", include("merchants.api_urls")),
    path("", include("merchants.urls")),
]
