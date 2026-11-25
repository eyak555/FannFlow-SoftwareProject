"""Racine des URL.

Les routes CRUD ne se déclarent pas ici. Chaque module a son propre urls.py,
déjà inclus ci-dessous. Une branche de module ne doit pas modifier ce fichier.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path


admin.site.site_header = "FannFlow"
admin.site.site_title = "FannFlow"
admin.site.index_title = "Administration"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("users/", include("users_teams.urls")),
    path("events/", include("events_program.urls")),
    path("registration/", include("registration_access.urls")),
    path("resources/", include("resources_operations.urls")),
    path("sponsors/", include("sponsors_finance.urls")),
    path("communication/", include("communication_media.urls")),
]

# Photos de profil servies par Django uniquement en développement.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = "core.views.page_not_found"
