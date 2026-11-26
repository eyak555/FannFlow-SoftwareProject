from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, TemplateView, UpdateView

from core.placeholders import render_crud_placeholder
from core.services import dashboard_data
from .entities import MODULE
from . import services
from .forms import (
    EventOrganizerAssignForm, EventOrganizerUpdateForm, LoginForm, PasswordSettingsForm, ProfileForm,
    RegisterForm, UserCreateForm, UserUpdateForm,
)
from .models import AccountActivity, EventOrganizer, User
from .permissions import AdministratorRequiredMixin, ManagementAccessRequiredMixin

USER_ENTITY = next(entity for entity in MODULE["entities"] if entity["slug"] == "users")


def get_home_url_for(user):
    """Redirection après connexion selon le rôle."""
    if user.has_management_access:
        return reverse("users_teams:home")
    return reverse("core:home")


# --- Authentification ----------------------------------------------------


class LoginView(auth_views.LoginView):
    template_name = "users_teams/auth/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True
    extra_context = {"page_title": "Connexion", "module": MODULE}

    def get_default_redirect_url(self):
        return get_home_url_for(self.request.user)

    def form_valid(self, form):
        response = super().form_valid(form)
        # L'espace de gestion salue déjà l'utilisateur : pas de message en double.
        if not form.get_user().has_management_access:
            messages.success(self.request, f"Bienvenue, {form.get_user().first_name} !")
        return response


class LogoutView(auth_views.LogoutView):
    """Déconnexion en POST uniquement (protection CSRF)."""

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        messages.info(request, "Vous êtes déconnecté.")
        return response


class RegisterView(CreateView):
    """Inscription publique réservée aux participants."""

    model = User
    form_class = RegisterForm
    template_name = "users_teams/auth/register.html"
    extra_context = {
        "page_title": "Créer un compte participant",
        "page_intro": "Inscrivez-vous pour réserver vos places et acheter vos billets.",
        "module": MODULE,
    }

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(get_home_url_for(request.user))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        login(self.request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(self.request, "Votre compte participant a été créé. Bienvenue sur FannFlow !")
        return redirect(get_home_url_for(user))


class PasswordForgottenView(TemplateView):
    """Sprint 1 : pas d'envoi d'email, la réinitialisation passe par un administrateur."""

    template_name = "users_teams/auth/password_forgotten.html"
    extra_context = {"page_title": "Mot de passe oublié", "module": MODULE}


# --- Espace de gestion ---------------------------------------------------


class DashboardView(ManagementAccessRequiredMixin, TemplateView):
    """Administrateur : tableau de bord du Module 1.
    Directeur / organisateur : tableau de bord opérationnel."""

    def get_template_names(self):
        if self.request.user.is_administrator:
            return ["users_teams/dashboard_admin.html"]
        return ["users_teams/dashboard.html"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_administrator:
            context.update(module=MODULE, page_title="Tableau de bord", admin=services.admin_dashboard())
            return context
        context.update(
            module=MODULE,
            page_title="Tableau de bord",
            page_intro=MODULE["summary"],
            stats={
                "total": User.objects.count(),
                "active": User.objects.filter(status=User.Status.ACTIVE).count(),
                "admins": User.objects.filter(role=User.Role.ADMIN).count(),
                "team": User.objects.exclude(business_role="").count(),
            },
            dashboard=dashboard_data(self.request.user),
        )
        return context


# Point d'entrée attendu par core.routing.crud_patterns (route « home »).
module_home = DashboardView.as_view()


def crud_placeholder(request, entity, action, pk=None):
    """Entités du module pas encore développées (profils, équipes…)."""
    return render_crud_placeholder(request, MODULE, entity, action, pk)


# --- CRUD Utilisateur (administrateurs uniquement) -----------------------


class UserContextMixin(AdministratorRequiredMixin):
    model = User
    page_title = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(module=MODULE, entity=USER_ENTITY, page_title=self.page_title)
        return context


class UserListView(UserContextMixin, ListView):
    template_name = "users_teams/user_list.html"
    context_object_name = "users"
    paginate_by = 10
    page_title = "Utilisateurs"

    SORT_OPTIONS = {
        "last_name": "Nom (A → Z)",
        "-last_name": "Nom (Z → A)",
        "first_name": "Prénom (A → Z)",
        "-first_name": "Prénom (Z → A)",
        "-created_at": "Plus récents",
        "created_at": "Plus anciens",
        "role": "Rôle (A → Z)",
        "-role": "Rôle (Z → A)",
    }
    DEFAULT_SORT = "last_name"

    def get_sort(self):
        sort = self.request.GET.get("sort", self.DEFAULT_SORT)
        return sort if sort in self.SORT_OPTIONS else self.DEFAULT_SORT

    def get_queryset(self):
        queryset = User.objects.all()
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query)
            )
        role = self.request.GET.get("role", "")
        if role in User.Role.values:
            queryset = queryset.filter(role=role)
        status = self.request.GET.get("status", "")
        if status in User.Status.values:
            queryset = queryset.filter(status=status)
        # --- Recherche avancée ---
        business_role = self.request.GET.get("business_role", "")
        if business_role in User.BusinessRole.values:
            queryset = queryset.filter(business_role=business_role)
        elif business_role == "none":
            queryset = queryset.filter(business_role="")
        created_from = parse_date(self.request.GET.get("created_from", "") or "")
        if created_from:
            queryset = queryset.filter(created_at__date__gte=created_from)
        created_to = parse_date(self.request.GET.get("created_to", "") or "")
        if created_to:
            queryset = queryset.filter(created_at__date__lte=created_to)
        connexion = self.request.GET.get("connexion", "")
        if connexion == "never":
            queryset = queryset.filter(last_login__isnull=True)
        elif connexion == "recent":
            queryset = queryset.filter(last_login__gte=timezone.now() - timedelta(days=30))
        elif connexion == "dormant":
            queryset = queryset.filter(last_login__lt=timezone.now() - timedelta(days=90))
        if self.request.GET.get("phone") == "1":
            queryset = queryset.exclude(phone="")
        sort = self.get_sort()
        tie_breaker = "first_name" if sort.lstrip("-") == "last_name" else "last_name"
        return queryset.order_by(sort, tie_breaker, "pk")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sort = self.get_sort()
        sortable = ("last_name", "first_name", "created_at", "role")
        context.update(
            # Cliquer sur une colonne déjà triée inverse l'ordre.
            next_sort={field: f"-{field}" if sort == field else field for field in sortable},
            sort_arrows={
                field: " ↑" if sort == field else " ↓" if sort == f"-{field}" else ""
                for field in sortable
            },
            filters={
                "q": self.request.GET.get("q", ""),
                "role": self.request.GET.get("role", ""),
                "status": self.request.GET.get("status", ""),
                "sort": self.get_sort(),
                "business_role": self.request.GET.get("business_role", ""),
                "created_from": self.request.GET.get("created_from", ""),
                "created_to": self.request.GET.get("created_to", ""),
                "connexion": self.request.GET.get("connexion", ""),
                "phone": self.request.GET.get("phone", ""),
            },
            advanced_active=any(
                self.request.GET.get(key) for key in ("business_role", "created_from", "created_to", "connexion", "phone")
            ),
            # ?avance=1 ouvre simplement le panneau (lien du tableau de bord).
            advanced_open=self.request.GET.get("avance") == "1",
            business_role_choices=User.BusinessRole.choices,
            connexion_choices=[
                ("never", "Jamais connecté"),
                ("recent", "Connecté ces 30 derniers jours"),
                ("dormant", "Sans connexion depuis 90 jours"),
            ],
            sort_options=self.SORT_OPTIONS,
            role_choices=User.Role.choices,
            status_choices=User.Status.choices,
            page_intro=f"{context['paginator'].count} utilisateur(s) trouvé(s).",
        )
        return context


class UserDetailView(UserContextMixin, DetailView):
    template_name = "users_teams/user_detail.html"
    context_object_name = "managed_user"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(page_title=str(self.object), pk=self.object.pk)
        return context


class UserCreateView(UserContextMixin, SuccessMessageMixin, CreateView):
    form_class = UserCreateForm
    template_name = "users_teams/user_form.html"
    page_title = "Nouvel utilisateur"
    success_message = "L’utilisateur « %(first_name)s %(last_name)s » a été créé."

    PRESET_TITLES = {
        User.Role.PARTICIPANT: "Nouveau compte participant",
        User.Role.ADMIN: "Nouveau compte administrateur",
    }

    def get_initial(self):
        """Préremplit le rôle depuis les cartes du tableau de bord (?role=…&business_role=…)."""
        initial = super().get_initial()
        role = self.request.GET.get("role", "")
        if role in User.Role.values:
            initial["role"] = role
        business_role = self.request.GET.get("business_role", "")
        if business_role in User.BusinessRole.values:
            initial["business_role"] = business_role
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        role = self.request.GET.get("role", "")
        if role in self.PRESET_TITLES:
            context["page_title"] = self.PRESET_TITLES[role]
        return context

    def get_success_url(self):
        return reverse("users_teams:user_detail", args=[self.object.pk])


class UserUpdateView(UserContextMixin, SuccessMessageMixin, UpdateView):
    form_class = UserUpdateForm
    template_name = "users_teams/user_form.html"
    context_object_name = "managed_user"
    success_message = "L’utilisateur « %(first_name)s %(last_name)s » a été modifié."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Modifier {self.object}"
        return context

    def form_valid(self, form):
        # Un administrateur ne peut pas retirer ses propres droits ni se désactiver.
        if self.object.pk == self.request.user.pk and (
            form.cleaned_data["role"] != User.Role.ADMIN
            or form.cleaned_data["status"] != User.Status.ACTIVE
        ):
            form.add_error(None, "Vous ne pouvez pas retirer votre propre rôle d’administrateur ni désactiver votre compte.")
            return self.form_invalid(form)
        before = services.snapshot(User.objects.get(pk=self.object.pk))
        response = super().form_valid(form)
        services.log_account_changes(before, self.object, self.request.user)
        return response

    def get_success_url(self):
        return reverse("users_teams:user_detail", args=[self.object.pk])


class UserDeleteView(UserContextMixin, DeleteView):
    template_name = "users_teams/user_confirm_delete.html"
    context_object_name = "managed_user"
    success_url = reverse_lazy("users_teams:user_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Supprimer un utilisateur"
        return context

    def form_valid(self, form):
        if self.object.pk == self.request.user.pk:
            messages.error(self.request, "Vous ne pouvez pas supprimer votre propre compte.")
            return redirect("users_teams:user_detail", pk=self.object.pk)
        name = str(self.object)
        services.log_activity(AccountActivity.Action.DELETED, self.object, self.request.user)
        if self.object.profile_picture:
            self.object.profile_picture.delete(save=False)
        response = super().form_valid(form)
        messages.success(self.request, f"L’utilisateur « {name} » a été supprimé.")
        return response


# --- Préférences (tout membre de l'équipe) ---------------------------------


class PreferencesMixin(ManagementAccessRequiredMixin):
    page_title = ""
    page_intro = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(module=MODULE, page_title=self.page_title, page_intro=self.page_intro)
        return context


class ProfileView(PreferencesMixin, SuccessMessageMixin, UpdateView):
    """Mon profil : informations personnelles de l'utilisateur connecté."""

    form_class = ProfileForm
    template_name = "users_teams/profile.html"
    page_title = "Mon profil"
    page_intro = "Vos informations personnelles. Le rôle et l’email sont gérés par un administrateur."
    success_message = "Votre profil a été mis à jour."
    success_url = reverse_lazy("users_teams:profile")

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        response = super().form_valid(form)
        services.log_activity(AccountActivity.Action.PROFILE_UPDATED, self.object, self.request.user)
        return response


class SettingsView(PreferencesMixin, SuccessMessageMixin, auth_views.PasswordChangeView):
    """Paramètres : sécurité du compte (mot de passe)."""

    form_class = PasswordSettingsForm
    template_name = "users_teams/settings.html"
    page_title = "Paramètres"
    page_intro = "Sécurité de votre compte."
    success_message = "Votre mot de passe a été modifié."
    success_url = reverse_lazy("users_teams:settings")


# --- Organisateurs d'événements --------------------------------------------


class OrganizersView(ManagementAccessRequiredMixin, ListView):
    """Directeurs et organisateurs, avec leurs affectations aux événements.

    Les affectations s'affichent dès que le Module 2 (Events & Program)
    fournit le modèle Événement ; aucun compte n'est créé ici.
    """

    template_name = "users_teams/organizers.html"
    context_object_name = "members"

    def get_queryset(self):
        queryset = User.objects.exclude(business_role="").order_by("business_role", "last_name", "first_name")
        business_role = self.request.GET.get("business_role", "")
        if business_role in User.BusinessRole.values:
            queryset = queryset.filter(business_role=business_role)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        assignments = services.event_assignments()
        context.update(
            module=MODULE,
            page_title="Organisateurs d’événements",
            page_intro="Directeurs et organisateurs, et leurs affectations aux événements.",
            rows=[{"user": m, "events": (assignments or {}).get(m.pk, [])} for m in context["members"]],
            events_available=assignments is not None,
            selected_business_role=self.request.GET.get("business_role", ""),
            business_role_choices=User.BusinessRole.choices,
            counts={
                "directors": User.objects.filter(business_role=User.BusinessRole.DIRECTOR).count(),
                "organizers": User.objects.filter(business_role=User.BusinessRole.ORGANIZER).count(),
            },
        )
        return context


# --- Affectation des organisateurs aux événements (Event Organizer) ---------
#
# Administrateur et directeur : CRUD complet.
# Organisateur : consultation de ses propres affectations uniquement.


def can_manage_assignments(user):
    return user.is_authenticated and (
        user.is_administrator or user.business_role == User.BusinessRole.DIRECTOR
    )


class AssignmentManagerRequiredMixin(ManagementAccessRequiredMixin):
    def test_func(self):
        return can_manage_assignments(self.request.user)


class AssignmentContextMixin:
    page_title = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(module=MODULE, page_title=self.page_title)
        return context


def assignment_list_url(event_id=None):
    url = reverse("users_teams:assignment_list")
    return f"{url}?event={event_id}" if event_id else url


class EventOrganizerListView(AssignmentContextMixin, ManagementAccessRequiredMixin, ListView):
    template_name = "users_teams/assignments/list.html"
    context_object_name = "assignments"
    paginate_by = 10
    page_title = "Affectations des organisateurs"

    SORT_OPTIONS = {
        "-assigned_at": "Plus récentes",
        "assigned_at": "Plus anciennes",
        "user__last_name": "Organisateur (A → Z)",
        "-user__last_name": "Organisateur (Z → A)",
        "event__start_date": "Date de l’événement",
        "status": "Statut",
    }

    def get_sort(self):
        sort = self.request.GET.get("sort", "-assigned_at")
        return sort if sort in self.SORT_OPTIONS else "-assigned_at"

    def get_queryset(self):
        queryset = EventOrganizer.objects.select_related("user", "event", "assigned_by")
        if not can_manage_assignments(self.request.user):
            queryset = queryset.filter(user=self.request.user)  # un organisateur ne voit que les siennes
        params = self.request.GET
        query = params.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query)
                | Q(user__email__icontains=query) | Q(event__title__icontains=query)
                | Q(task__icontains=query)
            )
        if params.get("event", "").isdecimal():
            queryset = queryset.filter(event_id=int(params["event"]))
        if params.get("status") in EventOrganizer.Status.values:
            queryset = queryset.filter(status=params["status"])
        if params.get("permissions") in EventOrganizer.Permission.values:
            queryset = queryset.filter(permissions=params["permissions"])
        return queryset.order_by(self.get_sort(), "pk")

    def get_context_data(self, **kwargs):
        from .forms import assignable_events

        context = super().get_context_data(**kwargs)
        params = self.request.GET
        selected_event = None
        if params.get("event", "").isdecimal():
            selected_event = assignable_events().model.objects.filter(pk=int(params["event"])).first()
        visible = EventOrganizer.objects.all()
        if not can_manage_assignments(self.request.user):
            visible = visible.filter(user=self.request.user)
        context.update(
            can_manage=can_manage_assignments(self.request.user),
            events=assignable_events(),
            selected_event=selected_event,
            filters={key: params.get(key, "") for key in ("q", "event", "status", "permissions")},
            sort=self.get_sort(),
            sort_options=self.SORT_OPTIONS,
            status_choices=EventOrganizer.Status.choices,
            permission_choices=EventOrganizer.Permission.choices,
            stats={
                "total": visible.count(),
                "active": visible.filter(status=EventOrganizer.Status.ACTIVE).count(),
                "events": visible.values("event").distinct().count(),
                "organizers": visible.values("user").distinct().count(),
            },
            page_intro=f"{context['paginator'].count} affectation(s) trouvée(s).",
        )
        return context


class EventOrganizerAssignView(AssignmentContextMixin, AssignmentManagerRequiredMixin, FormView):
    template_name = "users_teams/assignments/assign.html"
    form_class = EventOrganizerAssignForm
    page_title = "Affecter des organisateurs"

    def get_initial(self):
        initial = super().get_initial()
        if self.request.GET.get("event", "").isdecimal():
            initial["event"] = int(self.request.GET["event"])
        return initial

    def form_valid(self, form):
        event = form.cleaned_data["event"]
        new = form.cleaned_data["new_organizers"]
        EventOrganizer.objects.bulk_create([
            EventOrganizer(
                user=organizer, event=event, assigned_by=self.request.user,
                permissions=form.cleaned_data["permissions"], task=form.cleaned_data["task"],
            )
            for organizer in new
        ])
        messages.success(self.request, f"{len(new)} organisateur(s) affecté(s) à « {event} ».")
        if form.already_assigned:
            names = ", ".join(str(u) for u in form.already_assigned)
            messages.warning(self.request, f"Déjà affecté(s), ignoré(s) : {names}.")
        return redirect(assignment_list_url(event.pk))


class EventOrganizerUpdateView(AssignmentContextMixin, AssignmentManagerRequiredMixin, SuccessMessageMixin, UpdateView):
    model = EventOrganizer
    form_class = EventOrganizerUpdateForm
    template_name = "users_teams/assignments/update.html"
    context_object_name = "assignment"
    page_title = "Modifier l’affectation"
    success_message = "L’affectation a été modifiée."

    def get_success_url(self):
        return assignment_list_url(self.object.event_id)


class EventOrganizerDeleteView(AssignmentContextMixin, AssignmentManagerRequiredMixin, DeleteView):
    model = EventOrganizer
    template_name = "users_teams/assignments/confirm_delete.html"
    context_object_name = "assignment"
    page_title = "Retirer un organisateur"

    def get_success_url(self):
        return assignment_list_url(self.object.event_id)

    def form_valid(self, form):
        label = str(self.object.user)
        response = super().form_valid(form)
        messages.success(self.request, f"{label} a été retiré(e) de l’événement.")
        return response
