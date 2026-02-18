from django.contrib import admin

from .models import TalosEngram, TalosEngramTag


@admin.register(TalosEngramTag)
class TalosEngramTagAdmin(admin.ModelAdmin):
    list_display = ('name',)

@admin.register(TalosEngram)
class TalosEngramAdmin(admin.ModelAdmin):
    list_display = ('name', 'relevance_score', 'is_active', 'created')
    list_filter = ('is_active', 'tags', 'created')
    search_fields = ('name', 'description')
    filter_horizontal = ('tags', 'heads', 'sessions', 'source_turns')