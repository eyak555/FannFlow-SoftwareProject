from core.registry import get_modules


def navigation(request):
    return {"fannflow_modules": get_modules()}
