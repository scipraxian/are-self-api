from django.contrib import admin
from django.utils.html import format_html
from .models import (ReasoningStatus, ToolDefinition, ReasoningSession,
                     ReasoningGoal, ReasoningTurn, ToolCall, RelevantEngram)


class ToolCallInline(admin.TabularInline):
    model = ToolCall
    extra = 0
    readonly_fields = ('created', 'status', 'result_payload', 'traceback')
    can_delete = False


class ReasoningTurnInline(admin.TabularInline):
    model = ReasoningTurn
    extra = 0
    fields = ('turn_number', 'status', 'thought_preview', 'created')
    readonly_fields = ('thought_preview', 'created')
    show_change_link = True
    can_delete = False

    def thought_preview(self, obj):
        return obj.thought_process[:100] + "..."


@admin.register(ReasoningSession)
class ReasoningSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'status_badge', 'goal', 'turn_count', 'created')
    list_filter = ('status', 'created')
    inlines = [ReasoningTurnInline]  # Links Turns to Session

    def status_badge(self, obj):
        color = '#64748b'
        if obj.status.name == 'Active': color = '#eab308'
        if obj.status.name == 'Completed': color = '#22c55e'
        if obj.status.name in ['Error', 'Attention Required']: color = '#ef4444'
        return format_html(
            '<span style="color:white; background:{}; padding:4px 8px; border-radius:4px; font-weight:bold;">{}</span>',
            color, obj.status.name
        )

    def turn_count(self, obj):
        return obj.turns.count()


@admin.register(ReasoningTurn)
class ReasoningTurnAdmin(admin.ModelAdmin):
    list_display = ('session', 'turn_number', 'status', 'created')
    inlines = [ToolCallInline]  # Links Tools to Turn


# Register others
admin.site.register(ReasoningStatus)
admin.site.register(ToolDefinition)
admin.site.register(ReasoningGoal)
admin.site.register(RelevantEngram)
admin.site.register(ToolCall)