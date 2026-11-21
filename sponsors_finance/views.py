from core.placeholders import render_crud_placeholder, render_module_home
from .entities import MODULE

def module_home(request):
    return render_module_home(request, MODULE)

def crud_placeholder(request, entity, action, pk=None):
    return render_crud_placeholder(request, MODULE, entity, action, pk)
