from decimal import Decimal

from django.shortcuts import render
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, UpdateView, View

from users_teams.permissions import AdministratorRequiredMixin
from .entities import MODULE
from .forms import (
    AccessPointForm,
    AttendanceForm,
    CheckInForm,
    FreeTicketConfirmationForm,
    ParticipantRegistrationForm,
    PrototypePaymentForm,
    RegistrationForm,
    TicketForm,
    validate_event_registration,
)
from .models import AccessPoint, Attendance, Registration, Ticket
from .qr_codes import qr_code_data_uri
from .services import (
    create_registration_ticket,
    check_in_ticket,
    check_out_attendance,
    confirm_participant_registration,
    save_attendance,
    sync_registration_tickets,
    ticket_is_ready_for_qr,
)


class PaginationOptionsMixin:
    page_size_options = (10, 25, 50, 75, 100)
    default_page_size = 25

    def get_page_size(self):
        try:
            page_size = int(self.request.GET.get("per_page", self.default_page_size))
        except (TypeError, ValueError):
            return self.default_page_size
        return page_size if page_size in self.page_size_options else self.default_page_size

    def get_paginate_by(self, queryset):
        return self.get_page_size()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query_params = self.request.GET.copy()
        query_params.pop(self.page_kwarg, None)
        query_params["per_page"] = str(self.get_page_size())
        context["pagination_query"] = query_params.urlencode()
        filter_params = self.request.GET.copy()
        filter_params.pop(self.page_kwarg, None)
        filter_params.pop("per_page", None)
        context["pagination_filters"] = list(filter_params.items())
        context["page_size_options"] = self.page_size_options
        context["selected_page_size"] = self.get_page_size()
        return context


class RegistrationAccessListView(AdministratorRequiredMixin, PaginationOptionsMixin, ListView):
    pass


class RegistrationListView(RegistrationAccessListView):
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
                Q(user__first_name__icontains=self.search_query)
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


class RegistrationDetailView(AdministratorRequiredMixin, DetailView):
    model = Registration
    template_name = "registration_access/registrations/details.html"
    context_object_name = "registration"


class RegistrationCreateView(AdministratorRequiredMixin, CreateView):
    model = Registration
    template_name = "registration_access/registrations/forms.html"
    form_class = RegistrationForm
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "registrations"})

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            create_registration_ticket(self.object)
        return response


class RegistrationUpdateView(AdministratorRequiredMixin, UpdateView):
    model = Registration
    template_name = "registration_access/registrations/forms.html"
    form_class = RegistrationForm
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "registrations"})

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            sync_registration_tickets(self.object)
        return response


class RegistrationDeleteView(AdministratorRequiredMixin, DeleteView):
    model = Registration
    template_name = "registration_access/registrations/delete_confirmation.html"
    context_object_name = "registration"
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "registrations"})

    def form_valid(self, form):
        if self.object.tickets.filter(attendances__isnull=False).exists():
            messages.error(
                self.request,
                "Cette inscription possède des présences enregistrées. Supprimez d’abord les brouillons ; les entrées effectuées doivent être conservées.",
            )
            return HttpResponseRedirect(self.get_success_url())
        return super().form_valid(form)


class ParticipantRegistrationListView(LoginRequiredMixin, PaginationOptionsMixin, ListView):
    model = Registration
    template_name = "registration_access/participants/registrations.html"
    context_object_name = "registrations"

    def get_queryset(self):
        return Registration.objects.filter(user=self.request.user).prefetch_related("tickets")


class ParticipantRegistrationCreateView(LoginRequiredMixin, CreateView):
    model = Registration
    template_name = "registration_access/participants/registration_form.html"
    form_class = ParticipantRegistrationForm
    success_url = reverse_lazy("registration_access:my_registrations")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        event_id = self.request.GET.get("event_id", "")
        if event_id.isdecimal():
            from events_program.models import Event

            if Event.objects.filter(pk=int(event_id), status=Event.Status.PUBLISHED).exists():
                initial["event_id"] = int(event_id)
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event_id = self.request.POST.get("event_id") or self.request.GET.get("event_id", "")
        if event_id.isdecimal():
            from events_program.models import Event

            context["event"] = Event.objects.filter(
                pk=int(event_id),
                status=Event.Status.PUBLISHED,
            ).first()
        return context

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.status = Registration.STATUS_PENDING
        form.instance.payment_status = Registration.PAYMENT_PENDING
        with transaction.atomic():
            from events_program.models import Event

            event = Event.objects.select_for_update().filter(
                pk=form.cleaned_data["event_id"]
            ).first()
            if event is not None:
                try:
                    validate_event_registration(event, self.request.user)
                except ValidationError as error:
                    form.add_error("event_id", error)
                    return self.form_invalid(form)
            response = super().form_valid(form)
            create_registration_ticket(self.object)
        messages.success(
            self.request,
            "Votre demande est enregistrée. Retrouvez votre billet pour le confirmer gratuitement ou simuler le paiement ; aucun débit réel n’est effectué.",
        )
        return response


class ParticipantRegistrationCancelView(LoginRequiredMixin, View):
    def post(self, request, pk):
        registration = get_object_or_404(
            Registration,
            pk=pk,
            user=request.user,
        )
        can_cancel = (
            registration.status == Registration.STATUS_PENDING
            and registration.payment_status == Registration.PAYMENT_PENDING
            and not registration.tickets.filter(attendances__isnull=False).exists()
        )
        if not can_cancel:
            messages.error(
                request,
                "Seule une inscription en attente de paiement peut être annulée ici. Contactez l’administration pour toute autre demande.",
            )
        else:
            registration.status = Registration.STATUS_CANCELLED
            registration.save(update_fields=["status"])
            sync_registration_tickets(registration)
            messages.success(request, "Votre inscription a été annulée.")
        return redirect("registration_access:my_registrations")


class ParticipantRegistrationConfirmView(LoginRequiredMixin, FormView):
    template_name = "registration_access/participants/payment_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.registration = get_object_or_404(
            Registration.objects.prefetch_related("tickets"),
            pk=kwargs["pk"],
            user=request.user,
        )
        self.tickets = list(self.registration.tickets.all().order_by("pk"))
        if (
            self.registration.status != Registration.STATUS_PENDING
            or self.registration.payment_status != Registration.PAYMENT_PENDING
        ):
            messages.info(request, "Cette inscription a déjà été traitée.")
            return redirect("registration_access:my_tickets")
        if not self.tickets or any(
            ticket.status != Ticket.STATUS_PENDING for ticket in self.tickets
        ):
            messages.error(request, "Aucun billet en attente ne peut être confirmé.")
            return redirect("registration_access:my_tickets")
        self.total_amount = sum(
            (ticket.price for ticket in self.tickets),
            Decimal("0.00"),
        )
        self.payment_required = self.total_amount > Decimal("0.00")
        return super().dispatch(request, *args, **kwargs)

    def get_form_class(self):
        if self.payment_required:
            return PrototypePaymentForm
        return FreeTicketConfirmationForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            registration=self.registration,
            tickets=self.tickets,
            total_amount=self.total_amount,
            payment_required=self.payment_required,
        )
        return context

    def form_valid(self, form):
        try:
            registration = confirm_participant_registration(
                self.registration.pk,
                self.request.user,
            )
        except Registration.DoesNotExist as error:
            raise Http404 from error
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        else:
            if registration.payment_status == Registration.PAYMENT_PAID:
                messages.success(
                    self.request,
                    "Votre paiement de test est confirmé. Votre billet est activé.",
                )
            else:
                messages.success(self.request, "Votre billet gratuit est confirmé.")
        return redirect("registration_access:my_tickets")


class ParticipantTicketListView(LoginRequiredMixin, PaginationOptionsMixin, ListView):
    model = Ticket
    template_name = "registration_access/participants/tickets.html"
    context_object_name = "tickets"

    def get_queryset(self):
        return Ticket.objects.filter(
            registration__user=self.request.user
        ).select_related("registration")


class ParticipantTicketDetailView(LoginRequiredMixin, DetailView):
    model = Ticket
    template_name = "registration_access/tickets/details.html"
    context_object_name = "ticket"

    def get_queryset(self):
        return Ticket.objects.filter(registration__user=self.request.user).select_related(
            "registration",
            "registration__user",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if ticket_is_ready_for_qr(self.object):
            context["qr_code_image"] = qr_code_data_uri(self.object.code)
        return context


class TicketListView(RegistrationAccessListView):
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
                Q(code__icontains=self.search_query)
                | Q(registration__user__first_name__icontains=self.search_query)
                | Q(registration__user__last_name__icontains=self.search_query)
                | Q(registration__user__email__icontains=self.search_query)
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


class TicketDetailView(AdministratorRequiredMixin, DetailView):
    model = Ticket
    template_name = "registration_access/tickets/details.html"
    context_object_name = "ticket"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if ticket_is_ready_for_qr(self.object):
            context["qr_code_image"] = qr_code_data_uri(self.object.code)
        return context


class TicketCreateView(AdministratorRequiredMixin, CreateView):
    model = Ticket
    template_name = "registration_access/tickets/forms.html"
    form_class = TicketForm
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "tickets"})


class TicketUpdateView(AdministratorRequiredMixin, UpdateView):
    model = Ticket
    template_name = "registration_access/tickets/forms.html"
    form_class = TicketForm
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "tickets"})


class TicketDeleteView(AdministratorRequiredMixin, DeleteView):
    model = Ticket
    template_name = "registration_access/tickets/delete_confirmation.html"
    context_object_name = "ticket"
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "tickets"})

    def form_valid(self, form):
        if self.object.attendances.exists():
            messages.error(
                self.request,
                "Ce billet possède des présences liées et ne peut pas être supprimé.",
            )
            return HttpResponseRedirect(self.get_success_url())
        return super().form_valid(form)


class AttendanceListView(RegistrationAccessListView):
    model = Attendance
    template_name = "registration_access/attendances/list.html"
    context_object_name = "attendances"
    queryset = Attendance.objects.select_related(
        "ticket",
        "ticket__registration",
        "ticket__registration__user",
        "access_point",
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        self.search_query = self.request.GET.get("q", "").strip()
        self.selected_state = self.request.GET.get("state", "")

        if self.search_query:
            search_filter = (
                Q(access_point__name__icontains=self.search_query)
                | Q(ticket__code__icontains=self.search_query)
                | Q(ticket__registration__user__first_name__icontains=self.search_query)
                | Q(ticket__registration__user__last_name__icontains=self.search_query)
                | Q(ticket__registration__user__email__icontains=self.search_query)
            )
            queryset = queryset.filter(search_filter)

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


class AttendanceDetailView(AdministratorRequiredMixin, DetailView):
    model = Attendance
    template_name = "registration_access/attendances/details.html"
    context_object_name = "attendance"


class AttendanceCreateView(AdministratorRequiredMixin, CreateView):
    model = Attendance
    template_name = "registration_access/attendances/forms.html"
    form_class = AttendanceForm
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "attendances"})

    def form_valid(self, form):
        try:
            with transaction.atomic():
                self.object = save_attendance(form.save(commit=False))
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        return HttpResponseRedirect(self.get_success_url())


class AttendanceUpdateView(AdministratorRequiredMixin, UpdateView):
    model = Attendance
    template_name = "registration_access/attendances/forms.html"
    form_class = AttendanceForm
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "attendances"})

    def form_valid(self, form):
        try:
            with transaction.atomic():
                self.object = save_attendance(form.save(commit=False))
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        return HttpResponseRedirect(self.get_success_url())


class AttendanceDeleteView(AdministratorRequiredMixin, DeleteView):
    model = Attendance
    template_name = "registration_access/attendances/delete_confirmation.html"
    context_object_name = "attendance"
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "attendances"})

    def form_valid(self, form):
        if self.object.check_in:
            messages.error(
                self.request,
                "Une présence avec une entrée enregistrée ne peut pas être supprimée.",
            )
            return HttpResponseRedirect(self.get_success_url())
        return super().form_valid(form)


class AttendanceCheckInView(AdministratorRequiredMixin, FormView):
    template_name = "registration_access/attendances/check_in.html"
    form_class = CheckInForm
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "attendances"})

    def form_valid(self, form):
        try:
            attendance = check_in_ticket(
                form.cleaned_data["code"],
                form.cleaned_data["access_point"],
            )
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(
            self.request,
            f"Entrée enregistrée pour {attendance.ticket.registration.user}.",
        )
        return HttpResponseRedirect(
            reverse_lazy(
                "registration_access:entity_detail",
                kwargs={"entity": "attendances", "pk": attendance.pk},
            )
        )


class AttendanceCheckOutView(AdministratorRequiredMixin, View):
    def post(self, request, pk):
        try:
            attendance = check_out_attendance(pk)
        except ValidationError as error:
            messages.error(request, error.message)
        else:
            messages.success(
                request,
                f"Sortie enregistrée pour {attendance.ticket.registration.user}.",
            )
        return HttpResponseRedirect(
            reverse_lazy("registration_access:entity_list", kwargs={"entity": "attendances"})
        )


class AccessPointListView(RegistrationAccessListView):
    model = AccessPoint
    template_name = "registration_access/access_points/list.html"
    context_object_name = "access_points"

    def get_queryset(self):
        queryset = super().get_queryset().annotate(
            occupancy=Count(
                "attendances",
                filter=Q(
                    attendances__check_in__isnull=False,
                    attendances__check_out__isnull=True,
                ),
            )
        ).order_by("pk")
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
                on_site=Count(
                    "attendances",
                    filter=Q(
                        attendances__check_in__isnull=False,
                        attendances__check_out__isnull=True,
                    ),
                ),
            ),
        })
        return context


class AccessPointDetailView(AdministratorRequiredMixin, DetailView):
    model = AccessPoint
    template_name = "registration_access/access_points/details.html"
    context_object_name = "access_point"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_occupancy"] = self.object.current_occupancy
        return context


class AccessPointCreateView(AdministratorRequiredMixin, CreateView):
    model = AccessPoint
    template_name = "registration_access/access_points/forms.html"
    form_class = AccessPointForm
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "access-points"})


class AccessPointUpdateView(AdministratorRequiredMixin, UpdateView):
    model = AccessPoint
    template_name = "registration_access/access_points/forms.html"
    form_class = AccessPointForm
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "access-points"})


class AccessPointDeleteView(AdministratorRequiredMixin, DeleteView):
    model = AccessPoint
    template_name = "registration_access/access_points/delete_confirmation.html"
    context_object_name = "access_point"
    success_url = reverse_lazy("registration_access:entity_list", kwargs={"entity": "access-points"})

    def form_valid(self, form):
        if self.object.attendances.exists():
            messages.error(
                self.request,
                "Ce point d’accès possède des présences liées et ne peut pas être supprimé.",
            )
            return HttpResponseRedirect(self.get_success_url())
        return super().form_valid(form)


def module_home(request):
    is_administrator = (
        request.user.is_authenticated and request.user.is_administrator
    )
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
            "is_administrator": is_administrator,
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
