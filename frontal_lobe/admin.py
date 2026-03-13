from django.contrib import admin
from django.utils.html import format_html

from .models import (
    ChatMessage,
    ChatMessageRole,
    ModelRegistry,
    ReasoningGoal,
    ReasoningSession,
    ReasoningStatus,
    ReasoningTurn,
    SessionConclusion,
)


class ReasoningGoalInline(admin.TabularInline):
    model = ReasoningGoal
    extra = 0
    fields = ('status', 'rendered_goal', 'achieved', 'created')
    readonly_fields = ('created',)


class ReasoningTurnInline(admin.TabularInline):
    model = ReasoningTurn
    extra = 0
    fields = (
        'turn_number',
        'status',
        'tokens_input',
        'tokens_output',
        'inference_time',
    )
    readonly_fields = (
        'turn_number',
        'tokens_input',
        'tokens_output',
        'inference_time',
    )
    show_change_link = True


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    fk_name = 'turn'
    extra = 0
    fields = (
        'role',
        'session',
        'content',
        'tool_call',
        'is_volatile',
        'created',
    )
    readonly_fields = ('created',)


@admin.register(ReasoningSession)
class ReasoningSessionAdmin(admin.ModelAdmin):
    # Add 'launch_cortex' to your list_display
    list_display = (
        'id',
        'spike',
        'status',
        'launch_cortex',
        'max_turns',
        'created',
        'delta',
    )
    list_filter = ('status', 'created')
    search_fields = ('id', 'goals__rendered_goal')
    readonly_fields = ('created', 'modified', 'delta')
    list_select_related = ('status', 'identity_disc', 'participant', 'spike')
    inlines = [ReasoningGoalInline, ReasoningTurnInline]

    @admin.display(description='Interface')
    def launch_cortex(self, obj):
        """Generates a direct link to the LCARS Situation Room for this session."""
        url = f'/reasoning/{obj.id}/'
        return format_html(
            '<a class="button" href="{}" target="_blank" style="background-color: #f99f1b; color: #1a1a1a; font-weight: bold;">OPEN CORTEX</a>',
            url,
        )

    launch_cortex.short_description = 'Interface'


@admin.register(ReasoningGoal)
class ReasoningGoalAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'session',
        'status',
        'achieved',
        'short_goal',
        'created',
    )
    list_filter = ('status', 'achieved')
    search_fields = ('rendered_goal', 'session__id')
    list_select_related = ('session', 'status')

    def short_goal(self, obj):
        return (
            obj.rendered_goal[:50] + '...'
            if len(obj.rendered_goal) > 50
            else obj.rendered_goal
        )

    short_goal.short_description = 'Goal Preview'


@admin.register(ReasoningTurn)
class ReasoningTurnAdmin(admin.ModelAdmin):
    list_display = (
        'turn_number',
        'session',
        'status',
        'tokens_input',
        'tokens_output',
        'inference_time',
    )
    list_filter = ('status', 'created')
    search_fields = ('thought_process', 'session__id')
    list_select_related = ('session', 'status', 'last_turn')
    filter_horizontal = (
        'turn_goals',
    )  # Renders a nice dual-selector for the M2M field
    readonly_fields = ('created', 'modified', 'delta')
    inlines = [ChatMessageInline]


@admin.register(SessionConclusion)
class SessionConclusionAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'status', 'outcome_status')
    search_fields = (
        'summary',
        'reasoning_trace',
        'outcome_status',
        'session__id',
    )
    list_select_related = ('session', 'status')


@admin.register(ReasoningStatus)
class ReasoningStatusAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)


@admin.register(ModelRegistry)
class ModelRegistryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'api_variant')
    search_fields = ('name', 'api_variant')


@admin.register(ChatMessageRole)
class ChatMessageRoleAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'created')
    search_fields = ('name',)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'session',
        'turn',
        'role',
        'is_volatile',
        'created',
    )
    list_filter = ('role', 'is_volatile')
    search_fields = ('content', 'session__id', 'turn__id')
    list_select_related = ('session', 'turn', 'role', 'tool_call')
    readonly_fields = ('created',)
