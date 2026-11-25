from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from core.placeholders import render_crud_placeholder
from .entities import MODULE
from .forms import LoginForm, RegisterForm, UserCreateForm, UserUpdateForm
from .models import User
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
    template_name = "users_teams/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            module=MODULE,
            page_title="Espace de gestion",
            page_intro=MODULE["summary"],
            stats={
                "total": User.objects.count(),
                "active": User.objects.filter(status=User.Status.ACTIVE).count(),
                "admins": User.objects.filter(role=User.Role.ADMIN).count(),
                "team": User.objects.exclude(business_role="").count(),
            },
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
            },
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
        return super().form_valid(form)

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
        if self.object.profile_picture:
            self.object.profile_picture.delete(save=False)
        response = super().form_valid(form)
        messages.success(self.request, f"L’utilisateur « {name} » a été supprimé.")
        return response
