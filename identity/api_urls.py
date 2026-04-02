from rest_framework import routers

from .api import (
    BudgetPeriodViewSet,
    IdentityAddonViewSet,
    IdentityBudgetViewSet,
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
    r'identity-discs', IdentityDiscViewSet, basename='identitydiscs'
)
V2_IDENTITY_ROUTER.register(
    r'identity_addons', IdentityAddonViewSet, basename='identityaddons'
)
V2_IDENTITY_ROUTER.register(
    r'identity_tags', IdentityTagViewSet, basename='identitytags'
)
V2_IDENTITY_ROUTER.register(
    r'identity_types', IdentityTypeViewSet, basename='identitytypes'
)
V2_IDENTITY_ROUTER.register(
    r'budget-periods', BudgetPeriodViewSet, basename='budgetperiods'
)
V2_IDENTITY_ROUTER.register(
    r'identity-budgets', IdentityBudgetViewSet, basename='identitybudgets'
)
