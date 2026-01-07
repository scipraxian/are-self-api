from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.views import View
from .models import HydraSpellbook, HydraEnvironment
from .hydra import Hydra
from environments.models import ProjectEnvironment

class LaunchFastValidateView(View):
    def post(self, request):
        # 1. Get the "Fast Validate" Spellbook
        try:
            spellbook = HydraSpellbook.objects.get(name="Fast Validate")
        except HydraSpellbook.DoesNotExist:
            return render(request, 'hydra/partials/error.html', {
                'message': "Error: 'Fast Validate' Spellbook missing. Run fixtures."
            }, status=404)

        # 2. Get Active Environment
        env = ProjectEnvironment.objects.filter(is_active=True).first()
        if not env:
            return render(request, 'hydra/partials/error.html', {
                'message': "Error: No Active Environment found."
            }, status=400)

        # 3. Resolve Hydra Environment
        hydra_env, _ = HydraEnvironment.objects.get_or_create(
            project_environment=env,
            defaults={'name': f"Auto-Env for {env.name}"}
        )

        # 4. Initialize & Launch
        controller = Hydra(spellbook_id=spellbook.id, env_id=hydra_env.id)
        controller.start()

        # 5. Render Feedback Template
        return render(request, 'hydra/partials/spawn_feedback.html', {
            'spawn': controller.spawn
        })