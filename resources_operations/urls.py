from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "resources_operations"
urlpatterns = [
    path("", views.ModuleHomeView.as_view(), name="home"),
    path("connexion/", views.OperationsLoginView.as_view(), name="login"),
    path("deconnexion/", LogoutView.as_view(next_page="resources_operations:login"), name="logout"),
    path("evenements/", views.EventRequirementsView.as_view(), name="event_requirements"),
    path("evenements/<int:event_id>/besoins/", views.EventRequirementsEditView.as_view(), name="event_requirements_edit"),
    path("inventaire/", views.InventoryReportView.as_view(), name="inventory"),
    path("inventaire/export.pdf", views.InventoryExportView.as_view(), name="inventory_pdf"),
    path("allocations/optimiser/", views.AllocationPlanningView.as_view(), name="allocation_planning"),
    path("<slug:entity>/nouveau/", views.EntityCreateView.as_view(), name="entity_create"),
    path("<slug:entity>/<int:pk>/modifier/", views.EntityUpdateView.as_view(), name="entity_update"),
    path("<slug:entity>/<int:pk>/supprimer/", views.EntityDeleteView.as_view(), name="entity_delete"),
    path("<slug:entity>/<int:pk>/", views.EntityDetailView.as_view(), name="entity_detail"),
    path("<slug:entity>/", views.EntityListView.as_view(), name="entity_list"),
]
