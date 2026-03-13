from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from identity.models import Identity, IdentityDisc
from identity.serializers import IdentityDiscSerializer, IdentitySerializer


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
    def forge_disc(self, request, pk=None):
        """
        RTS Mechanic: Stamps a brand new Level 1 IdentityDisc from this Base Identity.
        Used when a user drags a Base Identity directly onto a Live Shift.
        """
        base_identity = self.get_object()

        # Optionally allow passing a custom name, otherwise generate one
        custom_name = request.data.get('name')
        new_name = (
            custom_name if custom_name else f'{base_identity.name} [Recruit]'
        )

        # Create the stateful instance
        new_disc = IdentityDisc.objects.create(
            name=new_name, identity=base_identity, level=1, xp=0, available=True
        )

        serializer = IdentityDiscSerializer(new_disc)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class IdentityDiscViewSet(viewsets.ModelViewSet):
    """
    The Barracks: Full CRUD access to the stateful, leveled-up AI instances.
    """

    queryset = (
        IdentityDisc.objects.select_related('ai_model', 'last_turn')
        .prefetch_related('memories')
        .all()
        .order_by('-level', '-xp', 'name')
    )
    serializer_class = IdentityDiscSerializer
