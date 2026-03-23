from rest_framework import viewsets

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


class IdentityAddonViewSet(viewsets.ModelViewSet):
    queryset = IdentityAddon.objects.all().order_by('name')
    serializer_class = IdentityAddonSerializer


class IdentityTagViewSet(viewsets.ModelViewSet):
    queryset = IdentityTag.objects.all().order_by('name')
    serializer_class = IdentityTagSerializer


class IdentityTypeViewSet(viewsets.ModelViewSet):
    queryset = IdentityType.objects.all().order_by('name')
    serializer_class = IdentityTypeSerializer
