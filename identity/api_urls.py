from rest_framework import routers

from .api import IdentityDiscViewSet, IdentityViewSet

V2_IDENTITY_ROUTER = routers.SimpleRouter()
V2_IDENTITY_ROUTER.register(
    r'identities', IdentityViewSet, basename='identities'
)
V2_IDENTITY_ROUTER.register(
    r'identity_discs', IdentityDiscViewSet, basename='identitydiscs'
)
