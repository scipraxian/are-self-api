from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from identity.models import (
    Identity,
    IdentityAddon,
    IdentityDisc,
    IdentityTag,
    IdentityType,
)
from identity.serializers import (
    IdentityAddonSerializer,
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
    def forge_disc(self, request, pk=None):
        """
        RTS Mechanic: Stamps a brand new Level 1 IdentityDisc from this Base Identity.
        Used when a user drags a Base Identity directly onto a Live Shift.
        """
        base_identity = self.get_object()

        # Optionally allow passing a custom name, otherwise generate one
        custom_name = request.data.get('name')
        new_name = (
            custom_name if custom_name else f'{base_identity.name} [Program]'
        )

        # 1. Create the Disc with the standard (Direct/ForeignKey) fields
        # Note: Use `ai_models` or `ai_model` depending on what you named it in models.py
        new_disc = IdentityDisc.objects.create(
            name=new_name,
            identity_type=base_identity.identity_type,
            system_prompt_template=base_identity.system_prompt_template,
            ai_model=base_identity.ai_model,
        )

        # 2. Copy the Many-to-Many relationships
        # This MUST happen after objects.create() so the new_disc has an ID
        new_disc.tags.set(base_identity.tags.all())
        new_disc.addons.set(base_identity.addons.all())
        new_disc.enabled_tools.set(base_identity.enabled_tools.all())

        # Return the fully fleshed out Disc to the frontend
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


class IdentityAddonViewSet(viewsets.ModelViewSet):
    queryset = IdentityAddon.objects.all().order_by('name')
    serializer_class = IdentityAddonSerializer


class IdentityTagViewSet(viewsets.ModelViewSet):
    queryset = IdentityTag.objects.all().order_by('name')
    serializer_class = IdentityTagSerializer


class IdentityTypeViewSet(viewsets.ModelViewSet):
    queryset = IdentityType.objects.all().order_by('name')
    serializer_class = IdentityTypeSerializer
