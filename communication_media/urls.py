from django.urls import path
from core.routing import crud_patterns
from . import views

app_name = "communication_media"


def entity_patterns(crud, list_view=None, detail_view=None):
    """Cinq routes CRUD d'une entité, sur les mêmes chemins que le socle.

    Les chemins reprennent le slug de ``entities.py`` : les noms génériques
    (``entity_list``, ``entity_create``…) utilisés par la navigation du socle
    mènent donc aussi à ces vues réelles.
    """
    slug, prefix = crud.slug, crud.url_prefix
    list_view = list_view or views.EntityListView.as_view(crud=crud)
    detail_view = detail_view or views.EntityDetailView.as_view(crud=crud)
    return [
        path(f"{slug}/", list_view, name=f"{prefix}_list"),
        path(f"{slug}/nouveau/", views.EntityCreateView.as_view(crud=crud), name=f"{prefix}_create"),
        path(f"{slug}/<int:pk>/", detail_view, name=f"{prefix}_detail"),
        path(f"{slug}/<int:pk>/modifier/", views.EntityUpdateView.as_view(crud=crud), name=f"{prefix}_update"),
        path(f"{slug}/<int:pk>/supprimer/", views.EntityDeleteView.as_view(crud=crud), name=f"{prefix}_delete"),
    ]


# Les routes réelles passent avant les routes génériques du socle
# (``crud_patterns``), qui ne servent plus que la page d'accueil du module.
urlpatterns = [
    path("media-contacts/", views.MediaContactListView.as_view(), name="media_contact_list"),
    path("media-contacts/nouveau/", views.MediaContactCreateView.as_view(), name="media_contact_create"),
    path("media-contacts/<int:pk>/", views.MediaContactDetailView.as_view(), name="media_contact_detail"),
    path("media-contacts/<int:pk>/modifier/", views.MediaContactUpdateView.as_view(), name="media_contact_update"),
    path("media-contacts/<int:pk>/supprimer/", views.MediaContactDeleteView.as_view(), name="media_contact_delete"),
    *entity_patterns(views.COMMUNICATION_CRUD),
    *entity_patterns(
        views.MEDIA_CRUD,
        list_view=views.MediaListView.as_view(),
        detail_view=views.MediaDetailView.as_view(),
    ),
    path("media/<int:pk>/fichier/", views.media_file, name="media_file"),
    *entity_patterns(views.PRESS_KIT_CRUD),
    *entity_patterns(views.PUBLICATION_CRUD),
    *crud_patterns(views),
]
