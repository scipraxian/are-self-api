from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View

from .models import ProjectEnvironment


class SelectEnvironmentView(View):
    """Toggles the selected environment."""

    def post(self, request, pk):
        env = get_object_or_404(ProjectEnvironment, pk=pk)
        if not env.available:
            messages.error(request, f'{env.name} is not available.')
            return HttpResponse('Environment Unavailable', status=403)
        env.selected = True
        env.save()

        messages.success(request, f'Target System Active: {env.name}')
        return redirect('dashboard:home')
