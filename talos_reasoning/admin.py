from django.contrib import admin
from .models import (ReasoningStatus, ToolDefinition, ReasoningSession,
                     ReasoningGoal, ReasoningTurn, ToolCall, RelevantEngram)


@admin.register(ReasoningStatus)
class ReasoningStatusAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')


@admin.register(ToolDefinition)
class ToolDefinitionAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_async', 'created')
    search_fields = ('name',)


@admin.register(ReasoningSession)
class ReasoningSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'max_turns', 'created')
    list_filter = ('status',)
    search_fields = ('goal',)


@admin.register(ReasoningGoal)
class ReasoningGoalAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'status', 'created')
    list_filter = ('status',)


@admin.register(ReasoningTurn)
class ReasoningTurnAdmin(admin.ModelAdmin):
    list_display = ('session', 'turn_number', 'status', 'created')
    list_filter = ('status',)


@admin.register(ToolCall)
class ToolCallAdmin(admin.ModelAdmin):
    list_display = ('tool', 'turn', 'status', 'created')
    list_filter = ('status', 'tool')


@admin.register(RelevantEngram)
class RelevantEngramAdmin(admin.ModelAdmin):
    list_display = ('session', 'relevance_score', 'is_active', 'created')
    list_filter = ('is_active',)
