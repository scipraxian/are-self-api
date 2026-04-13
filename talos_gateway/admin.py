"""Django admin for talos_gateway."""

from django.contrib import admin

from talos_gateway.models import GatewaySession, GatewaySessionStatus


@admin.register(GatewaySessionStatus)
class GatewaySessionStatusAdmin(admin.ModelAdmin):
    """Admin for gateway session status lookup."""

    list_display = ('id', 'name')


@admin.register(GatewaySession)
class GatewaySessionAdmin(admin.ModelAdmin):
    """Admin for gateway sessions."""

    list_display = (
        'id',
        'platform',
        'channel_id',
        'status',
        'last_activity',
        'reasoning_session',
    )
    list_filter = ('platform', 'status')
