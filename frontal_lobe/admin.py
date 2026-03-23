# from django.contrib import admin
# from django.utils.html import format_html
#
# from .models import (
#     ModelProvider,
#     ModelRegistry,
#     ReasoningSession,
#     ReasoningStatus,
#     ReasoningTurn,
#     SessionConclusion,
# )
#
#
# class ReasoningTurnInline(admin.TabularInline):
#     model = ReasoningTurn
#     extra = 0
#     fields = (
#         'turn_number',
#         'status',
#         'tokens_input',
#         'tokens_output',
#         'inference_time',
#     )
#     readonly_fields = (
#         'turn_number',
#         'tokens_input',
#         'tokens_output',
#         'inference_time',
#     )
#     show_change_link = True
#

#
# @admin.register(ReasoningSession)
# class ReasoningSessionAdmin(admin.ModelAdmin):
#     # Add 'launch_cortex' to your list_display
#     list_display = (
#         'id',
#         'spike',
#         'status',
#         'launch_cortex',
#         'max_turns',
#         'created',
#         'delta',
#     )
#     list_filter = ('status', 'created')
#     search_fields = ('id',)
#     readonly_fields = ('created', 'modified', 'delta')
#     list_select_related = ('status', 'identity_disc', 'participant', 'spike')
#     inlines = [ReasoningTurnInline]
#
#     @admin.display(description='Interface')
#     def launch_cortex(self, obj):
#         """Generates a direct link to the LCARS Situation Room for this session."""
#         url = f'/reasoning/{obj.id}/'
#         return format_html(
#             '<a class="button" href="{}" target="_blank" style="background-color: #f99f1b; color: #1a1a1a; font-weight: bold;">OPEN CORTEX</a>',
#             url,
#         )
#
#     launch_cortex.short_description = 'Interface'
#
#
# @admin.register(ReasoningTurn)
# class ReasoningTurnAdmin(admin.ModelAdmin):
#     list_display = (
#         'turn_number',
#         'session',
#         'status',
#         'tokens_input',
#         'tokens_output',
#         'inference_time',
#     )
#     list_filter = ('status', 'created')
#     search_fields = ('thought_process', 'session__id')
#     list_select_related = ('session', 'status', 'last_turn')
#     readonly_fields = ('created', 'modified', 'delta')
#
# @admin.register(SessionConclusion)
# class SessionConclusionAdmin(admin.ModelAdmin):
#     list_display = ('id', 'session', 'status', 'outcome_status')
#     search_fields = (
#         'summary',
#         'reasoning_trace',
#         'outcome_status',
#         'session__id',
#     )
#     list_select_related = ('session', 'status')
#
#
# @admin.register(ReasoningStatus)
# class ReasoningStatusAdmin(admin.ModelAdmin):
#     list_display = ('id', 'name')
#     search_fields = ('name',)
#
#
# @admin.register(ModelProvider)
# class ModelProviderAdmin(admin.ModelAdmin):
#     list_display = (
#         'id',
#         'name',
#     )
#     search_fields = ('name',)
#
#
# @admin.register(ModelRegistry)
# class ModelRegistryAdmin(admin.ModelAdmin):
#     list_display = ('id', 'name', 'api_variant')
#     search_fields = ('name', 'api_variant')
#

