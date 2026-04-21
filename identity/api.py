from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from hypothalamus.hypothalamus import Hypothalamus

from identity.forge import forge_identity_disc
from identity.models import (
    BudgetPeriod,
    Identity,
    IdentityAddon,
    IdentityBudget,
    IdentityDisc,
    IdentityTag,
    IdentityType,
)
from identity.serializers import (
    BudgetPeriodSerializer,
    IdentityAddonSerializer,
    IdentityBudgetSerializer,
    IdentityDiscSerializer,
    IdentitySerializer,
    IdentityTagSerializer,
    IdentityTypeSerializer,
)


class IdentityViewSet(viewsets.ModelViewSet):
    """
    The Foundry: Read-only access to base Identity templates.
    """

    queryset = (
        Identity.objects.prefetch_related('tags', 'addons', 'enabled_tools')
        .select_related('identity_type')
        .all()
        .order_by('name')
    )
    serializer_class = IdentitySerializer

    @action(detail=True, methods=['post'], url_path='forge')
    def forge(self, request, pk=None):
        """Stamp a new Level 1 IdentityDisc from this base Identity."""
        base_identity = self.get_object()
        custom_name = request.data.get('name') if request.data else None
        new_disc = forge_identity_disc(base_identity, custom_name=custom_name)
        serializer = IdentityDiscSerializer(new_disc, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class IdentityDiscViewSet(viewsets.ModelViewSet):
    """
    The Barracks: Full CRUD access to the stateful, leveled-up AI instances.
    """

    queryset = (
        IdentityDisc.objects.select_related('last_turn')
        .prefetch_related('memories')
        .all()
        .order_by('-level', '-xp', 'name')
    )
    serializer_class = IdentityDiscSerializer

    @action(detail=True, methods=['get'], url_path='model-preview')
    def model_preview(self, request, pk=None):
        """Return the AIModelProvider the Hypothalamus would select right now.

        Pure read — no ledger record is created or mutated.
        """
        disc = self.get_object()
        best = Hypothalamus.preview_model_selection(disc)

        if not best:
            return Response({
                'model_provider': None,
                'model_name': None,
                'provider_name': None,
                'provider_model_id': None,
                'reason': 'No eligible model found for current routing config.',
            })

        pricing = best.aimodelpricing_set.filter(is_current=True).first()

        return Response({
            'model_provider': best.id,
            'ai_model_id': str(best.ai_model.id),
            'model_name': best.ai_model.name,
            'provider_name': best.provider.name,
            'provider_model_id': best.provider_unique_model_id,
            'input_cost_per_token': str(pricing.input_cost_per_token) if pricing else None,
            'output_cost_per_token': str(pricing.output_cost_per_token) if pricing else None,
        })


class IdentityAddonViewSet(viewsets.ModelViewSet):
    queryset = IdentityAddon.objects.all().order_by('name')
    serializer_class = IdentityAddonSerializer


class IdentityTagViewSet(viewsets.ModelViewSet):
    queryset = IdentityTag.objects.all().order_by('name')
    serializer_class = IdentityTagSerializer


class IdentityTypeViewSet(viewsets.ModelViewSet):
    queryset = IdentityType.objects.all().order_by('name')
    serializer_class = IdentityTypeSerializer


class BudgetPeriodViewSet(viewsets.ModelViewSet):
    queryset = BudgetPeriod.objects.all()
    serializer_class = BudgetPeriodSerializer


class IdentityBudgetViewSet(viewsets.ModelViewSet):
    queryset = IdentityBudget.objects.all()
    serializer_class = IdentityBudgetSerializer
