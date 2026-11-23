from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import User

PASSWORD = "Str0ng-Pass!2026"
NEW_PASSWORD = "An0ther-Pass!2026"


def make_user(email, role=User.Role.PARTICIPANT, **extra):
    extra.setdefault("first_name", "Test")
    extra.setdefault("last_name", "User")
    return User.objects.create_user(email=email, password=PASSWORD, role=role, **extra)


def user_payload(**overrides):
    data = {
        "first_name": "Nour",
        "last_name": "Ben Salah",
        "email": "nour@example.tn",
        "phone": "+216 20 123 456",
        "birth_date": "1998-04-12",
        "role": User.Role.PARTICIPANT,
        "business_role": User.BusinessRole.ORGANIZER,
        "status": User.Status.ACTIVE,
        "password1": PASSWORD,
        "password2": PASSWORD,
    }
    data.update(overrides)
    return data


class UserCrudTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin@test.tn", role=User.Role.ADMIN, first_name="Ada", last_name="Min")
        self.client.force_login(self.admin)

    def test_list_displays_users(self):
        make_user("zied@test.tn", first_name="Zied", last_name="Trabelsi")
        response = self.client.get(reverse("users_teams:user_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "zied@test.tn")

    def test_list_search_sort_and_pagination(self):
        for index in range(12):
            make_user(f"user{index:02d}@test.tn", last_name=f"Nom{index:02d}")
        make_user("cible@test.tn", first_name="Cible", last_name="Unique")

        response = self.client.get(reverse("users_teams:user_list"), {"q": "unique"})
        self.assertEqual(list(response.context["users"]), [User.objects.get(email="cible@test.tn")])

        response = self.client.get(reverse("users_teams:user_list"), {"role": User.Role.ADMIN})
        self.assertEqual(list(response.context["users"]), [self.admin])

        response = self.client.get(reverse("users_teams:user_list"), {"sort": "-last_name"})
        self.assertEqual(response.context["users"][0].last_name, "Unique")

        response = self.client.get(reverse("users_teams:user_list"), {"page": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["users"]), 4)  # 14 comptes, 10 par page

    def test_create_valid_user_hashes_password(self):
        response = self.client.post(reverse("users_teams:user_create"), user_payload())
        user = User.objects.get(email="nour@example.tn")
        self.assertRedirects(response, reverse("users_teams:user_detail", args=[user.pk]))
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))
        self.assertEqual(user.business_role, User.BusinessRole.ORGANIZER)
        self.assertIsNotNone(user.created_at)
        self.assertIsNone(user.last_login)

    def test_create_requires_password_confirmation(self):
        response = self.client.post(
            reverse("users_teams:user_create"), user_payload(password1="", password2="")
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors["password1"])
        self.assertFalse(User.objects.filter(email="nour@example.tn").exists())

    def test_create_rejects_password_mismatch(self):
        response = self.client.post(
            reverse("users_teams:user_create"), user_payload(password2="Different-123!")
        )
        self.assertIn("password2", response.context["form"].errors)

    def test_create_rejects_duplicate_email_case_insensitive(self):
        make_user("nour@example.tn")
        response = self.client.post(
            reverse("users_teams:user_create"), user_payload(email="NOUR@Example.tn")
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)
        self.assertEqual(User.objects.filter(email__iexact="nour@example.tn").count(), 1)

    def test_create_rejects_invalid_role_and_missing_names(self):
        response = self.client.post(
            reverse("users_teams:user_create"),
            user_payload(role="superadmin", first_name="", last_name=""),
        )
        errors = response.context["form"].errors
        self.assertIn("role", errors)
        self.assertIn("first_name", errors)
        self.assertIn("last_name", errors)

    @override_settings(MEDIA_ROOT="media_test")
    def test_create_rejects_non_image_profile_picture(self):
        payload = user_payload(profile_picture=SimpleUploadedFile("script.exe", b"MZ"))
        response = self.client.post(reverse("users_teams:user_create"), payload)
        self.assertIn("profile_picture", response.context["form"].errors)

    def test_detail_never_shows_password_hash(self):
        user = make_user("voir@test.tn")
        response = self.client.get(reverse("users_teams:user_detail", args=[user.pk]))
        self.assertContains(response, "voir@test.tn")
        self.assertNotContains(response, user.password)
        self.assertNotContains(response, "pbkdf2")

    def test_update_with_empty_password_keeps_it(self):
        user = make_user("edit@test.tn")
        old_hash = user.password
        response = self.client.post(
            reverse("users_teams:user_update", args=[user.pk]),
            user_payload(email="edit@test.tn", first_name="Modifié", password1="", password2=""),
        )
        self.assertRedirects(response, reverse("users_teams:user_detail", args=[user.pk]))
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Modifié")
        self.assertEqual(user.password, old_hash)

    def test_update_with_new_password_rehashes_it(self):
        user = make_user("edit@test.tn")
        self.client.post(
            reverse("users_teams:user_update", args=[user.pk]),
            user_payload(email="edit@test.tn", password1=NEW_PASSWORD, password2=NEW_PASSWORD),
        )
        user.refresh_from_db()
        self.assertTrue(user.check_password(NEW_PASSWORD))
        self.assertNotEqual(user.password, NEW_PASSWORD)

    def test_update_rejects_email_of_another_user(self):
        make_user("pris@test.tn")
        user = make_user("edit@test.tn")
        response = self.client.post(
            reverse("users_teams:user_update", args=[user.pk]),
            user_payload(email="pris@test.tn", password1="", password2=""),
        )
        self.assertIn("email", response.context["form"].errors)

    def test_admin_cannot_demote_himself(self):
        response = self.client.post(
            reverse("users_teams:user_update", args=[self.admin.pk]),
            user_payload(email=self.admin.email, role=User.Role.PARTICIPANT, password1="", password2=""),
        )
        self.assertEqual(response.status_code, 200)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, User.Role.ADMIN)

    def test_delete_requires_confirmation_then_deletes(self):
        user = make_user("delete@test.tn")
        url = reverse("users_teams:user_delete", args=[user.pk])
        response = self.client.get(url)
        self.assertContains(response, "Confirmer la suppression")
        self.assertTrue(User.objects.filter(pk=user.pk).exists())

        response = self.client.post(url)
        self.assertRedirects(response, reverse("users_teams:user_list"))
        self.assertFalse(User.objects.filter(pk=user.pk).exists())

    def test_admin_cannot_delete_himself(self):
        self.client.post(reverse("users_teams:user_delete", args=[self.admin.pk]))
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())


class AccessControlTests(TestCase):
    def setUp(self):
        self.target = make_user("cible@test.tn")
        self.crud_urls = [
            reverse("users_teams:user_list"),
            reverse("users_teams:user_create"),
            reverse("users_teams:user_detail", args=[self.target.pk]),
            reverse("users_teams:user_update", args=[self.target.pk]),
            reverse("users_teams:user_delete", args=[self.target.pk]),
        ]

    def test_visitor_is_redirected_to_login(self):
        for url in self.crud_urls + [reverse("users_teams:home")]:
            response = self.client.get(url)
            self.assertRedirects(response, f"{reverse('users_teams:login')}?next={url}")

    def test_participant_is_forbidden(self):
        self.client.force_login(make_user("participant@test.tn"))
        for url in self.crud_urls + [reverse("users_teams:home")]:
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_organizer_reaches_dashboard_but_not_user_crud(self):
        organizer = make_user("orga@test.tn", business_role=User.BusinessRole.ORGANIZER)
        self.client.force_login(organizer)
        self.assertEqual(self.client.get(reverse("users_teams:home")).status_code, 200)
        for url in self.crud_urls:
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_participant_cannot_delete_via_post(self):
        self.client.force_login(make_user("participant@test.tn"))
        self.client.post(reverse("users_teams:user_delete", args=[self.target.pk]))
        self.assertTrue(User.objects.filter(pk=self.target.pk).exists())


class AuthenticationTests(TestCase):
    def login(self, email, password=PASSWORD):
        return self.client.post(reverse("users_teams:login"), {"username": email, "password": password})

    def test_login_page_renders_mockup(self):
        response = self.client.get(reverse("users_teams:login"))
        self.assertContains(response, "Se connecter")
        self.assertContains(response, "Continuer avec Google")
        self.assertContains(response, reverse("users_teams:register"))
        self.assertContains(response, reverse("users_teams:password_forgotten"))
        self.assertNotContains(response, "placeholder-note")

    def test_admin_is_redirected_to_dashboard(self):
        make_user("admin@test.tn", role=User.Role.ADMIN)
        self.assertRedirects(self.login("admin@test.tn"), reverse("users_teams:home"))

    def test_organizer_is_redirected_to_dashboard(self):
        make_user("orga@test.tn", business_role=User.BusinessRole.ORGANIZER)
        self.assertRedirects(self.login("orga@test.tn"), reverse("users_teams:home"))

    def test_participant_is_redirected_to_home(self):
        make_user("participant@test.tn")
        self.assertRedirects(self.login("participant@test.tn"), reverse("core:home"))

    def test_login_is_case_insensitive_and_updates_last_login(self):
        user = make_user("casse@test.tn")
        self.login("CASSE@Test.tn")
        user.refresh_from_db()
        self.assertIsNotNone(user.last_login)

    def test_wrong_password_is_rejected(self):
        make_user("participant@test.tn")
        response = self.login("participant@test.tn", "wrong-password")
        self.assertContains(response, "Email ou mot de passe incorrect.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_account_is_rejected(self):
        make_user("inactif@test.tn", status=User.Status.INACTIVE)
        response = self.login("inactif@test.tn")
        self.assertContains(response, "Ce compte est inactif")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_requires_post(self):
        self.client.force_login(make_user("participant@test.tn"))
        self.assertEqual(self.client.get(reverse("users_teams:logout")).status_code, 405)
        response = self.client.post(reverse("users_teams:logout"))
        self.assertRedirects(response, reverse("core:home"))
        self.assertNotIn("_auth_user_id", self.client.session)


class RegistrationTests(TestCase):
    def payload(self, **overrides):
        data = user_payload(email="inscrit@test.tn")
        for field in ("role", "business_role", "status"):
            data.pop(field)
        data.update(overrides)
        return data

    def test_register_forces_participant_role(self):
        response = self.client.post(
            reverse("users_teams:register"),
            self.payload(role=User.Role.ADMIN, business_role=User.BusinessRole.DIRECTOR),
        )
        self.assertRedirects(response, reverse("core:home"))
        user = User.objects.get(email="inscrit@test.tn")
        self.assertEqual(user.role, User.Role.PARTICIPANT)
        self.assertEqual(user.business_role, "")
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password(PASSWORD))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_register_rejects_duplicate_email(self):
        make_user("inscrit@test.tn")
        response = self.client.post(reverse("users_teams:register"), self.payload())
        self.assertIn("email", response.context["form"].errors)

    def test_register_rejects_weak_password(self):
        response = self.client.post(
            reverse("users_teams:register"), self.payload(password1="123", password2="123")
        )
        self.assertIn("password1", response.context["form"].errors)
        self.assertFalse(User.objects.filter(email="inscrit@test.tn").exists())

    def test_register_form_has_no_role_fields(self):
        response = self.client.get(reverse("users_teams:register"))
        self.assertNotContains(response, 'name="role"')
        self.assertNotContains(response, 'name="business_role"')
