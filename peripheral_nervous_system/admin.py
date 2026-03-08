from django.contrib import admin

from .models import (
    NerveTerminalEvent,
    NerveTerminalRegistry,
    NerveTerminalStatus,
    NerveTerminalTelemetry,
)


@admin.register(NerveTerminalStatus)
class NerveTerminalStatusAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')


@admin.register(NerveTerminalRegistry)
class NerveTerminalRegistryAdmin(admin.ModelAdmin):
    list_display = ('hostname', 'ip_address', 'version', 'status', 'last_seen')
    list_filter = ('status', 'version')
    search_fields = ('hostname', 'ip_address')


@admin.register(NerveTerminalTelemetry)
class NerveTerminalTelemetryAdmin(admin.ModelAdmin):
    list_display = (
        'target',
        'timestamp',
        'cpu_usage',
        'memory_usage_mb',
        'is_alive',
    )
    readonly_fields = ('timestamp', 'raw_payload')
    list_filter = ('target', 'timestamp')


@admin.register(NerveTerminalEvent)
class NerveTerminalEventAdmin(admin.ModelAdmin):
    list_display = ('target', 'event_type', 'timestamp', 'message')
    list_filter = ('event_type', 'target')
