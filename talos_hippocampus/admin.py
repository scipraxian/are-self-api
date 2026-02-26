from django.contrib import admin

from .models import TalosEngram, TalosEngramTag


@admin.register(TalosEngramTag)
class TalosEngramTagAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(TalosEngram)
class TalosEngramAdmin(admin.ModelAdmin):
    # Core list view for quick scanning of memory entropy
    list_display = ('name', 'relevance_score', 'is_active', 'created')
    list_filter = ('is_active', 'tags', 'created')
    search_fields = ('name', 'description')

    # Use filter_horizontal for the ManyToMany biological links
    filter_horizontal = ('tags', 'heads', 'sessions', 'source_turns')

    # Set the vector as read-only to prevent manual corruption of the embedding
    readonly_fields = ('created', 'modified', 'vector')

    fieldsets = (
        (
            'Identity',
            {'fields': ('name', 'description', 'relevance_score', 'is_active')},
        ),
        (
            'Biological Context',
            {
                'fields': ('tags', 'sessions', 'heads', 'source_turns'),
                'description': 'Relational links to the sessions and turns where this memory originated.',
            },
        ),
        (
            'Mathematical Lobe',
            {
                'fields': ('vector',),
                'description': 'The 768-dimension embedding used for Cosine Similarity and Auto-Recall defense.',
            },
        ),
        (
            'System Timestamps',
            {
                'fields': ('created', 'modified'),
                'classes': ('collapse',),
            },
        ),
    )
