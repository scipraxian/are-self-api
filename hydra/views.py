from django.shortcuts import render, get_object_or_404
from django.views import View
from .models import HydraSpellbook, HydraEnvironment
from .hydra import Hydra
from environments.models import ProjectEnvironment
import logging

logger = logging.getLogger(__name__)

class LaunchSpellbookView(View):
    def post(self, request, spellbook_id):
        # 1. Get the Spellbook (Clean UUID lookup)
        try:
            spellbook = HydraSpellbook.objects.get(id=spellbook_id)
        except HydraSpellbook.DoesNotExist:
            return render(request, 'hydra/partials/error.html', {
                'message': f"Error: Spellbook {spellbook_id} not found."
            }, status=404)

        logger.info(f"[HYDRA] Launching Spellbook: {spellbook.name} ({spellbook.id})")

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
        try:
            controller = Hydra(spellbook_id=spellbook.id, env_id=hydra_env.id)
            controller.start()
        except Exception as e:
            logger.exception("[HYDRA] Controller Start Failed")
            return render(request, 'hydra/partials/error.html', {
                'message': f"Controller Error: {str(e)}"
            }, status=500)

        return render(request, 'hydra/partials/spawn_feedback.html', {
            'spawn': controller.spawn
        })