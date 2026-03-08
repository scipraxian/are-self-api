from rest_framework import routers

from identity.api import IdentityDiscViewSet, IdentityViewSet

V2_IDENTITY_ROUTER = routers.SimpleRouter()
V2_IDENTITY_ROUTER.register(
    r'identities', IdentityViewSet, basename='identities'
)
V2_IDENTITY_ROUTER.register(
    r'identity-discs', IdentityDiscViewSet, basename='identity-discs'
)
