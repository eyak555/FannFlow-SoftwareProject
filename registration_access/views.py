from django.shortcuts import render
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .entities import MODULE
from .forms import AccessPointForm, AttendanceForm, RegistrationForm, TicketForm
from .models import AccessPoint, Attendance, Registration, Ticket
from .qr_codes import qr_code_data_uri
from .services import (
    create_registration_ticket,
    sync_registration_tickets,
    ticket_is_ready_for_qr,
)


class RegistrationListView(ListView):
    model = Registration
    template_name = "registration_access/registrations/list.html"
    context_object_name = "registrations"
    queryset = Registration.objects.select_related("user")

    def get_queryset(self):
        queryset = super().get_queryset()
        self.search_query = self.request.GET.get("q", "").strip()
        self.selected_status = self.request.GET.get("status", "")
        self.selected_payment = self.request.GET.get("payment", "")

        if self.search_query:
            search_filter = (
                Q(user__username__icontains=self.search_query)
                | Q(user__first_name__icontains=self.search_query)
                | Q(user__last_name__icontains=self.search_query)
                | Q(user__email__icontains=self.search_query)
                | Q(ticket_type__icontains=self.search_query)
            )
            if self.search_query.isdecimal():
                search_filter |= Q(event_id=int(self.search_query))
            queryset = queryset.filter(search_filter)

        valid_statuses = {value for value, _ in Registration.STATUS_CHOICES}
        if self.selected_status in valid_statuses:
            queryset = queryset.filter(status=self.selected_status)

        valid_payments = {value for value, _ in Registration.PAYMENT_CHOICES}
        if self.selected_payment in valid_payments:
            queryset = queryset.filter(payment_status=self.selected_payment)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "search_query": self.search_query,
            "selected_status": self.selected_status,
            "selected_payment": self.selected_payment,
            "status_choices": Registration.STATUS_CHOICES,
            "payment_choices": Registration.PAYMENT_CHOICES,
            "registration_stats": Registration.objects.aggregate(
                total=Count("pk"),
                confirmed=Count(
                    "pk",
                    filter=Q(status=Registration.STATUS_CONFIRMED),
                ),
                pending=Count(
                    "pk",
                    filter=Q(status=Registration.STATUS_PENDING),
                ),
                paid=Count(
                    "pk",
                    filter=Q(payment_status=Registration.PAYMENT_PAID),
                ),
            ),
        })
        return context


class RegistrationDetailView(DetailView):
    model = Registration
    template_name = "registration_access/registrations/details.html"
    context_object_name = "registration"


class RegistrationCreateView(CreateView):
    model = Registration
    template_name = "registration_access/registrations/forms.html"
    form_class = RegistrationForm
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "registrations"})

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            create_registration_ticket(self.object)
        return response


class RegistrationUpdateView(UpdateView):
    model = Registration
    template_name = "registration_access/registrations/forms.html"
    form_class = RegistrationForm
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "registrations"})

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            sync_registration_tickets(self.object)
        return response


class RegistrationDeleteView(DeleteView):
    model = Registration
    template_name = "registration_access/registrations/delete_confirmation.html"
    context_object_name = "registration"
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "registrations"})


class TicketListView(ListView):
    model = Ticket
    template_name = "registration_access/tickets/list.html"
    context_object_name = "tickets"
    queryset = Ticket.objects.select_related("registration", "registration__user")

    def get_queryset(self):
        queryset = super().get_queryset()
        self.search_query = self.request.GET.get("q", "").strip()
        self.selected_status = self.request.GET.get("status", "")
        self.selected_category = self.request.GET.get("category", "")

        if self.search_query:
            search_filter = (
                Q(qr_code__icontains=self.search_query)
                | Q(registration__user__username__icontains=self.search_query)
                | Q(registration__user__first_name__icontains=self.search_query)
                | Q(registration__user__last_name__icontains=self.search_query)
            )
            queryset = queryset.filter(search_filter)

        valid_statuses = {value for value, _ in Ticket.STATUS_CHOICES}
        if self.selected_status in valid_statuses:
            queryset = queryset.filter(status=self.selected_status)

        valid_categories = {value for value, _ in Ticket.CATEGORY_CHOICES}
        if self.selected_category in valid_categories:
            queryset = queryset.filter(category=self.selected_category)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "search_query": self.search_query,
            "selected_status": self.selected_status,
            "selected_category": self.selected_category,
            "status_choices": Ticket.STATUS_CHOICES,
            "category_choices": Ticket.CATEGORY_CHOICES,
            "ticket_stats": Ticket.objects.aggregate(
                total=Count("pk"),
                pending=Count("pk", filter=Q(status=Ticket.STATUS_PENDING)),
                available=Count("pk", filter=Q(status=Ticket.STATUS_AVAILABLE)),
                used=Count("pk", filter=Q(status=Ticket.STATUS_USED)),
                cancelled=Count("pk", filter=Q(status=Ticket.STATUS_CANCELLED)),
            ),
        })
        return context


class TicketDetailView(DetailView):
    model = Ticket
    template_name = "registration_access/tickets/details.html"
    context_object_name = "ticket"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if ticket_is_ready_for_qr(self.object):
            context["qr_code_image"] = qr_code_data_uri(self.object.qr_code)
        return context


class TicketCreateView(CreateView):
    model = Ticket
    template_name = "registration_access/tickets/forms.html"
    form_class = TicketForm
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "tickets"})


class TicketUpdateView(UpdateView):
    model = Ticket
    template_name = "registration_access/tickets/forms.html"
    form_class = TicketForm
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "tickets"})


class TicketDeleteView(DeleteView):
    model = Ticket
    template_name = "registration_access/tickets/delete_confirmation.html"
    context_object_name = "ticket"
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "tickets"})


class AttendanceListView(ListView):
    model = Attendance
    template_name = "registration_access/attendances/list.html"
    context_object_name = "attendances"
    queryset = Attendance.objects.select_related(
        "ticket",
        "ticket__registration",
        "ticket__registration__user",
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        self.search_query = self.request.GET.get("q", "").strip()
        self.selected_state = self.request.GET.get("state", "")

        if self.search_query:
            queryset = queryset.filter(
                Q(gate__icontains=self.search_query)
                | Q(ticket__qr_code__icontains=self.search_query)
                | Q(ticket__registration__user__username__icontains=self.search_query)
                | Q(ticket__registration__user__first_name__icontains=self.search_query)
                | Q(ticket__registration__user__last_name__icontains=self.search_query)
            )

        if self.selected_state == "checked_in":
            queryset = queryset.filter(
                check_in__isnull=False,
                check_out__isnull=True,
            )
        elif self.selected_state == "checked_out":
            queryset = queryset.filter(check_out__isnull=False)
        elif self.selected_state == "not_checked":
            queryset = queryset.filter(
                check_in__isnull=True,
                check_out__isnull=True,
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "search_query": self.search_query,
            "selected_state": self.selected_state,
            "attendance_stats": Attendance.objects.aggregate(
                total=Count("pk"),
                on_site=Count(
                    "pk",
                    filter=Q(check_in__isnull=False, check_out__isnull=True),
                ),
                checked_out=Count("pk", filter=Q(check_out__isnull=False)),
                not_checked=Count(
                    "pk",
                    filter=Q(check_in__isnull=True, check_out__isnull=True),
                ),
            ),
        })
        return context


class AttendanceDetailView(DetailView):
    model = Attendance
    template_name = "registration_access/attendances/details.html"
    context_object_name = "attendance"


class AttendanceCreateView(CreateView):
    model = Attendance
    template_name = "registration_access/attendances/forms.html"
    form_class = AttendanceForm
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "attendances"})


class AttendanceUpdateView(UpdateView):
    model = Attendance
    template_name = "registration_access/attendances/forms.html"
    form_class = AttendanceForm
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "attendances"})


class AttendanceDeleteView(DeleteView):
    model = Attendance
    template_name = "registration_access/attendances/delete_confirmation.html"
    context_object_name = "attendance"
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "attendances"})


class AccessPointListView(ListView):
    model = AccessPoint
    template_name = "registration_access/access_points/list.html"
    context_object_name = "access_points"

    def get_queryset(self):
        queryset = super().get_queryset()
        self.search_query = self.request.GET.get("q", "").strip()
        if self.search_query:
            search_filter = (
                Q(name__icontains=self.search_query)
                | Q(location__icontains=self.search_query)
            )
            if self.search_query.isdecimal():
                search_filter |= Q(event_id=int(self.search_query))
            queryset = queryset.filter(search_filter)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "search_query": self.search_query,
            "access_point_stats": AccessPoint.objects.aggregate(
                total=Count("pk"),
                capacity=Sum("capacity"),
            ),
        })
        return context


class AccessPointDetailView(DetailView):
    model = AccessPoint
    template_name = "registration_access/access_points/details.html"
    context_object_name = "access_point"


class AccessPointCreateView(CreateView):
    model = AccessPoint
    template_name = "registration_access/access_points/forms.html"
    form_class = AccessPointForm
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "access-points"})


class AccessPointUpdateView(UpdateView):
    model = AccessPoint
    template_name = "registration_access/access_points/forms.html"
    form_class = AccessPointForm
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "access-points"})


class AccessPointDeleteView(DeleteView):
    model = AccessPoint
    template_name = "registration_access/access_points/delete_confirmation.html"
    context_object_name = "access_point"
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "access-points"})


def module_home(request):
    access_areas = [
        {
            "slug": "registrations",
            "title": "Inscriptions",
            "description": "Suivez les demandes, les participants et leurs paiements.",
            "icon": "registration",
        },
        {
            "slug": "tickets",
            "title": "Billets",
            "description": "Gérez les billets émis, leurs catégories et leur validité.",
            "icon": "ticket",
        },
        {
            "slug": "attendances",
            "title": "Présences",
            "description": "Consultez les entrées et sorties des participants.",
            "icon": "attendance",
        },
        {
            "slug": "access-points",
            "title": "Points d’accès",
            "description": "Organisez les entrées, emplacements et capacités.",
            "icon": "access",
        },
    ]
    return render(
        request,
        "registration_access/home.html",
        {
            "module": MODULE,
            "page_title": MODULE["title"],
            "page_intro": MODULE["summary"],
            "access_areas": access_areas,
        },
    )


ENTITY_VIEWS = {
    "registrations": {
        "list": RegistrationListView,
        "create": RegistrationCreateView,
        "detail": RegistrationDetailView,
        "update": RegistrationUpdateView,
        "delete": RegistrationDeleteView,
    },
    "tickets": {
        "list": TicketListView,
        "create": TicketCreateView,
        "detail": TicketDetailView,
        "update": TicketUpdateView,
        "delete": TicketDeleteView,
    },
    "attendances": {
        "list": AttendanceListView,
        "create": AttendanceCreateView,
        "detail": AttendanceDetailView,
        "update": AttendanceUpdateView,
        "delete": AttendanceDeleteView,
    },
    "access-points": {
        "list": AccessPointListView,
        "create": AccessPointCreateView,
        "detail": AccessPointDetailView,
        "update": AccessPointUpdateView,
        "delete": AccessPointDeleteView,
    },
}


def entity_view(action):
    def dispatch(request, entity, **kwargs):
        from django.http import Http404

        views = ENTITY_VIEWS.get(entity)
        if views is None:
            raise Http404
        return views[action].as_view()(request, **kwargs)

    return dispatch
