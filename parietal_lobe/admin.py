from django.contrib import admin

from .models import (
    ParameterEnum,
    ToolCall,
    ToolDefinition,
    ToolParameter,
    ToolParameterAssignment,
    ToolParameterType,
    ToolUseType,
)


@admin.register(ToolParameterType)
class ToolParameterTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')


class ToolParameterAssignmentInline(admin.TabularInline):
    model = ToolParameterAssignment
    extra = 1
    autocomplete_fields = ['parameter']


@admin.register(ToolDefinition)
class ToolDefinitionAdmin(admin.ModelAdmin):
    list_display = ('name', 'use_type', 'is_async', 'description', 'genome')
    list_filter = ('genome',)
    search_fields = ('name',)
    inlines = [ToolParameterAssignmentInline]


class ParameterEnumInline(admin.TabularInline):
    model = ParameterEnum
    extra = 1


@admin.register(ToolParameter)
class ToolParameterAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'description', 'genome')
    list_filter = ('genome', 'type')
    search_fields = ('name',)
    inlines = [ParameterEnumInline]


@admin.register(ToolParameterAssignment)
class ToolParameterAssignmentAdmin(admin.ModelAdmin):
    list_display = ('tool', 'parameter', 'required', 'genome')
    list_filter = ('genome', 'tool', 'required')
    search_fields = ('tool__name', 'parameter__name')


@admin.register(ToolCall)
class ToolCallAdmin(admin.ModelAdmin):
    list_display = ('id', 'turn', 'tool', 'status')
    list_filter = ('status', 'tool')
    search_fields = ('arguments', 'call_id')
    readonly_fields = ('created', 'modified')


@admin.register(ToolUseType)
class ToolUseTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)
