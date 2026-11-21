from django.shortcuts import render


def home(request):
    return render(request, "core/home.html", {"page_title": "Accueil"})


def page_not_found(request, exception):
    return render(
        request,
        "404.html",
        {"page_title": "Page introuvable"},
        status=404,
    )
