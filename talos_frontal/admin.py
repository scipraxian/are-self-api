from django.contrib import admin
from django.utils.html import format_html
from .models import (
    ConsciousStream,
    ConsciousStatus,
    SystemDirective,
    SystemDirectiveIdentifier
)


@admin.register(ConsciousStatus)
class ConsciousStatusAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    ordering = ('id',)


@admin.register(SystemDirectiveIdentifier)
class SystemDirectiveIdentifierAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    ordering = ('id',)


@admin.register(SystemDirective)
class SystemDirectiveAdmin(admin.ModelAdmin):
    list_display = ('identifier', 'version', 'is_active', 'created', 'variable_preview')
    list_filter = ('identifier', 'is_active')
    readonly_fields = ('version', 'created', 'modified')
    search_fields = ('template',)

    fieldsets = (
        ('Identification', {
            'fields': ('identifier', 'version', 'is_active')
        }),
        ('Content', {
            'fields': ('template',),
            'description': 'Use {variable_name} syntax for dynamic injection.'
        }),
        ('Meta', {
            'fields': ('created', 'modified'),
            'classes': ('collapse',)
        })
    )

    def variable_preview(self, obj):
        """Shows which variables are required by this template."""
        vars = obj.required_variables
        if not vars:
            return "-"
        return ", ".join(vars)

    variable_preview.short_description = "Required Variables"


@admin.register(ConsciousStream)
class ConsciousStreamAdmin(admin.ModelAdmin):
    list_display = ('id', 'status_badge', 'spawn_link', 'head_link', 'short_thought', 'created')
    list_filter = ('status', 'created')
    readonly_fields = ('created', 'modified')
    search_fields = ('current_thought',)
    list_select_related = ('status', 'spawn_link', 'head_link')

    def status_badge(self, obj):
        """Color-coded status badge."""
        colors = {
            'Thinking': '#eab308',  # Yellow
            'Waiting': '#3b82f6',  # Blue
            'Done': '#22c55e',  # Green
        }
        color = colors.get(obj.status.name, '#64748b')  # Default Gray
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 10px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.status.name
        )

    status_badge.short_description = "Status"

    def short_thought(self, obj):
        """Truncates the thought for the list view."""
        return (obj.current_thought[:75] + '...') if len(obj.current_thought) > 75 else obj.current_thought

    short_thought.short_description = "Current Thought"