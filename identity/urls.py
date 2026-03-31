from rest_framework import routers

from identity.api import (
    IdentityAddonViewSet,
    IdentityDiscViewSet,
    IdentityTagViewSet,
    IdentityTypeViewSet,
    IdentityViewSet,
)

V2_IDENTITY_ROUTER = routers.SimpleRouter()
V2_IDENTITY_ROUTER.register(
    r'identities', IdentityViewSet, basename='identities'
)
V2_IDENTITY_ROUTER.register(
    r'identity-discs', IdentityDiscViewSet, basename='identity-discs'
)
V2_IDENTITY_ROUTER.register(
    r'identity-addons', IdentityAddonViewSet, basename='identity-addons'
)
V2_IDENTITY_ROUTER.register(
    r'identity-tags', IdentityTagViewSet, basename='identity-tags'
)
V2_IDENTITY_ROUTER.register(
    r'identity-types', IdentityTypeViewSet, basename='identity-types'
)
