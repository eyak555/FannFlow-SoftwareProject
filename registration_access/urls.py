from django.urls import path

from . import views

app_name = "registration_access"

urlpatterns = [
    path("", views.module_home, name="home"),
    path("<slug:entity>/nouveau/", views.entity_view("create"), name="entity_create"),
    path("<slug:entity>/<int:pk>/modifier/", views.entity_view("update"), name="entity_update"),
    path("<slug:entity>/<int:pk>/supprimer/", views.entity_view("delete"), name="entity_delete"),
    path("<slug:entity>/<int:pk>/", views.entity_view("detail"), name="entity_detail"),
    path("<slug:entity>/", views.entity_view("list"), name="entity_list"),
]
