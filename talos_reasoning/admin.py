from django.contrib import admin

from talos_parietal.models import ToolCall, ToolDefinition

from .models import (
    ModelRegistry,
    ReasoningGoal,
    ReasoningSession,
    ReasoningTurn,
    SessionConclusion,
)


class ToolCallInline(admin.StackedInline):
    model = ToolCall
    extra = 0
    readonly_fields = (
        'tool',
        'arguments',
        'result_payload',
        'traceback',
        'created',
        'status',
    )
    classes = ['collapse']


class ReasoningTurnInline(admin.StackedInline):
    model = ReasoningTurn
    extra = 0
    readonly_fields = (
        'turn_number',
        'input_context_snapshot',
        'thought_process',
        'created',
        'status',
    )
    inlines = [ToolCallInline]
    classes = ['collapse']


@admin.register(ReasoningSession)
class ReasoningSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'head', 'created', 'status')
    list_filter = ('status', 'created')
    search_fields = ('id',)
    readonly_fields = ('created', 'modified')
    inlines = [ReasoningTurnInline]


@admin.register(ToolDefinition)
class ToolDefinitionAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_async', 'description')


@admin.register(ModelRegistry)
class ModelRegistryAdmin(admin.ModelAdmin):
    list_display = ('name', 'api_variant', 'context_window_size')


@admin.register(SessionConclusion)
class SessionConclusionAdmin(admin.ModelAdmin):
    list_display = ('session', 'outcome_status', 'recommended_action')
