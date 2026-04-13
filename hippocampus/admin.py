from django.contrib import admin

from .models import Engram, EngramTag, SkillEngram, SkillFileAttachment


@admin.register(EngramTag)
class EngramTagAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Engram)
class EngramAdmin(admin.ModelAdmin):
    # Core list view for quick scanning of memory entropy
    list_display = ('name', 'relevance_score', 'is_active', 'created')
    list_filter = ('is_active', 'tags', 'created')
    search_fields = ('name', 'description')

    # Use filter_horizontal for the ManyToMany biological links
    filter_horizontal = (
        'tags',
        'spikes',
        'sessions',
        'source_turns',
        'identity_discs',
    )

    # Set the vector as read-only to prevent manual corruption of the embedding
    readonly_fields = ('created', 'modified', 'vector_display')

    def vector_display(self, obj):
        """Displays the vector in a format that avoids truthiness ambiguity."""
        if obj.vector is None:
            return 'None'
        return f'Vector({len(obj.vector)} dimensions)'

    vector_display.short_description = 'Vector'

    fieldsets = (
        (
            'Identity',
            {
                'fields': (
                    'name',
                    'description',
                    'relevance_score',
                    'is_active',
                    'creator',
                    'identity_discs',
                )
            },
        ),
        (
            'Biological Context',
            {
                'fields': ('tags', 'sessions', 'spikes', 'source_turns'),
                'description': 'Relational links to the sessions and turns where this memory originated.',
            },
        ),
        (
            'Mathematical Lobe',
            {
                'fields': ('vector_display',),
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


class SkillFileAttachmentInline(admin.TabularInline):
    model = SkillFileAttachment
    extra = 0
    readonly_fields = ('created',)
    fields = ('file_type', 'file_path', 'file_content', 'created')


@admin.register(SkillEngram)
class SkillEngramAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'is_active', 'created')
    list_filter = ('is_active', 'category')
    search_fields = ('name', 'description', 'body')
    readonly_fields = ('created', 'modified', 'vector_display')
    inlines = [SkillFileAttachmentInline]

    def vector_display(self, obj):
        """Displays the vector dimensions or None."""
        if obj.vector is None:
            return 'None'
        return f'Vector({len(obj.vector)} dimensions)'

    vector_display.short_description = 'Vector'

    fieldsets = (
        (
            None,
            {
                'fields': (
                    'name',
                    'description',
                    'category',
                    'is_active',
                    'identity_disc',
                )
            },
        ),
        (
            'Content',
            {
                'fields': ('body', 'yaml_frontmatter'),
            },
        ),
        (
            'Embedding',
            {
                'fields': ('vector_display',),
                'classes': ('collapse',),
            },
        ),
        (
            'Timestamps',
            {
                'fields': ('created', 'modified'),
                'classes': ('collapse',),
            },
        ),
    )
