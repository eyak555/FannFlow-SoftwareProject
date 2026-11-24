from django.urls import path
from core.routing import crud_patterns
from . import views

app_name = "communication_media"

# Les routes réelles de l'annuaire presse passent avant les routes génériques :
# « media-contacts/... » est servi ici, les autres entités gardent leur placeholder.
# Les noms génériques (entity_list, entity_create...) avec le slug
# « media-contacts » mènent donc aussi à ces vues.
urlpatterns = [
    path("media-contacts/", views.MediaContactListView.as_view(), name="media_contact_list"),
    path("media-contacts/nouveau/", views.MediaContactCreateView.as_view(), name="media_contact_create"),
    path("media-contacts/<int:pk>/", views.MediaContactDetailView.as_view(), name="media_contact_detail"),
    path("media-contacts/<int:pk>/modifier/", views.MediaContactUpdateView.as_view(), name="media_contact_update"),
    path("media-contacts/<int:pk>/supprimer/", views.MediaContactDeleteView.as_view(), name="media_contact_delete"),
    *crud_patterns(views),
]
