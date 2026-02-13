import logging

from django.db.models import Q
from django.views.generic import TemplateView

from environments.models import ProjectEnvironment
from hydra.models import HydraSpellbook

logger = logging.getLogger(__name__)


class DashboardHomeView(TemplateView):
    template_name = 'dashboard/mission_control.html'

    def get_context_data(self, **kwargs):
        # We keep the environment/library context for the sidebar,
        # but strip out ALL mission/swimlane logic.
        context = super().get_context_data(**kwargs)
        envs = list(ProjectEnvironment.objects.all().order_by('name'))
        active_env = next((e for e in envs if e.selected), None)
        context['environments'] = envs
        context['active_environment'] = active_env

        if active_env:
            all_books = (
                HydraSpellbook.objects.filter(
                    Q(environment=active_env) | Q(environment__isnull=True)
                )
                .prefetch_related('tags')
                .order_by('name')
            )
        else:
            all_books = HydraSpellbook.objects.prefetch_related(
                'tags'
            ).order_by('name')

        favorites, uncategorized = [], []
        tagged_groups = {}

        for book in all_books:
            if book.is_favorite:
                favorites.append(book)
            tags = book.tags.all()
            if tags:
                for tag in tags:
                    tagged_groups.setdefault(tag.name, []).append(book)
            else:
                uncategorized.append(book)

        context['favorites'] = favorites
        context['tagged_groups'] = [
            {'name': k, 'books': v} for k, v in sorted(tagged_groups.items())
        ]
        context['uncategorized'] = uncategorized

        return context
