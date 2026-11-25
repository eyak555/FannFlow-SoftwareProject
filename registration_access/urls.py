from django.urls import path

from . import views

app_name = "registration_access"

urlpatterns = [
    path("", views.module_home, name="home"),
    path("mes-inscriptions/", views.ParticipantRegistrationListView.as_view(), name="my_registrations"),
    path("mes-inscriptions/nouvelle/", views.ParticipantRegistrationCreateView.as_view(), name="registration_request"),
    path("mes-inscriptions/<int:pk>/annuler/", views.ParticipantRegistrationCancelView.as_view(), name="registration_cancel"),
    path("mes-inscriptions/<int:pk>/confirmer/", views.ParticipantRegistrationConfirmView.as_view(), name="registration_confirm"),
    path("mes-billets/", views.ParticipantTicketListView.as_view(), name="my_tickets"),
    path("mes-billets/<int:pk>/", views.ParticipantTicketDetailView.as_view(), name="my_ticket_detail"),
    path("attendances/check-in/", views.AttendanceCheckInView.as_view(), name="attendance_check_in"),
    path("attendances/<int:pk>/check-out/", views.AttendanceCheckOutView.as_view(), name="attendance_check_out"),
    path("<slug:entity>/nouveau/", views.entity_view("create"), name="entity_create"),
    path("<slug:entity>/<int:pk>/modifier/", views.entity_view("update"), name="entity_update"),
    path("<slug:entity>/<int:pk>/supprimer/", views.entity_view("delete"), name="entity_delete"),
    path("<slug:entity>/<int:pk>/", views.entity_view("detail"), name="entity_detail"),
    path("<slug:entity>/", views.entity_view("list"), name="entity_list"),
]
