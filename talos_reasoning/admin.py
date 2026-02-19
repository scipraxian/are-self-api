from django.contrib import admin

from .models import (
    ReasoningGoal,
    ReasoningSession,
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
    fields = ('turn_number', 'status', 'tokens_input', 'tokens_output', 'inference_time')
    readonly_fields = ('turn_number', 'tokens_input', 'tokens_output', 'inference_time')
    show_change_link = True

@admin.register(ReasoningSession)
class ReasoningSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'head', 'status', 'max_turns', 'created', 'delta')
    list_filter = ('status', 'created')
    search_fields = ('id', 'head__id', 'goals__rendered_goal')
    readonly_fields = ('created', 'modified', 'delta')
    inlines = [ReasoningGoalInline, ReasoningTurnInline]

@admin.register(ReasoningGoal)
class ReasoningGoalAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'status', 'achieved', 'short_goal', 'created')
    list_filter = ('status', 'achieved')
    search_fields = ('rendered_goal', 'session__id')

    def short_goal(self, obj):
        return obj.rendered_goal[:50] + '...' if len(obj.rendered_goal) > 50 else obj.rendered_goal
    short_goal.short_description = 'Goal Preview'

@admin.register(ReasoningTurn)
class ReasoningTurnAdmin(admin.ModelAdmin):
    list_display = ('turn_number', 'session', 'status', 'tokens_input', 'tokens_output', 'inference_time')
    list_filter = ('status', 'created')
    search_fields = ('thought_process', 'session__id')
    filter_horizontal = ('turn_goals',) # Renders a nice dual-selector for the M2M field
    readonly_fields = ('created', 'modified', 'delta')

@admin.register(SessionConclusion)
class SessionConclusionAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'status', 'outcome_status')
    search_fields = ('summary', 'reasoning_trace', 'outcome_status', 'session__id')