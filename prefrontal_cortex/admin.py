from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import PFCComment, PFCEpic, PFCItemStatus, PFCStory, PFCTask


@admin.register(PFCItemStatus)
class ItemStatusAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)


# ==========================================
# COMMENT INLINES (Tailored per Model)
# ==========================================


class EpicCommentInline(admin.TabularInline):
    model = PFCComment
    extra = 1
    fields = ('user', 'text', 'created')
    readonly_fields = ('created',)
    exclude = ('story', 'task')


class StoryCommentInline(admin.TabularInline):
    model = PFCComment
    extra = 1
    fields = ('user', 'text', 'created')
    readonly_fields = ('created',)
    exclude = ('epic', 'task')


class TaskCommentInline(admin.TabularInline):
    model = PFCComment
    extra = 1
    fields = ('user', 'text', 'created')
    readonly_fields = ('created',)
    exclude = ('epic', 'story')


# ==========================================
# HIERARCHY INLINES (The Agile Board)
# ==========================================


class PFCTaskInline(admin.TabularInline):
    """Allows creating/editing Tasks directly from a Story."""

    model = PFCTask
    extra = 0
    fields = ('name', 'status', 'description')
    show_change_link = True  # Adds a direct link to the full Task edit page


class PFCStoryInline(admin.TabularInline):
    """Allows creating/editing Stories directly from an Epic."""

    model = PFCStory
    extra = 0
    fields = ('name', 'status', 'description')
    show_change_link = True  # Adds a direct link to the full Story edit page


# ==========================================
# PRIMARY ADMIN INTERFACES
# ==========================================


@admin.register(PFCEpic)
class PFCEpicAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'story_count', 'created', 'modified')
    list_filter = ('status',)
    search_fields = ('name', 'description')
    readonly_fields = ('created', 'modified', 'delta', 'vector')

    # Nested Creation: Stories and Comments
    inlines = [PFCStoryInline, EpicCommentInline]

    fieldsets = (
        ('Strategic Directive', {'fields': ('name', 'description', 'status')}),
        (
            'Mathematical Lobe',
            {
                'fields': ('vector',),
                'classes': ('collapse',),
                'description': 'The 768-dimension embedding used for routing.',
            },
        ),
        (
            'System Timestamps',
            {
                'fields': ('created', 'modified', 'delta'),
                'classes': ('collapse',),
            },
        ),
    )

    def story_count(self, obj):
        count = obj.stories.count()
        return format_html(f'<b>{count}</b>')

    story_count.short_description = 'Stories'


@admin.register(PFCStory)
class PFCStoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'epic_link', 'status', 'task_count', 'modified')
    list_filter = ('status', 'epic')
    search_fields = ('name', 'description', 'epic__name')
    readonly_fields = ('created', 'modified', 'delta', 'vector', 'epic_link')

    # Nested Creation: Tasks and Comments
    inlines = [PFCTaskInline, StoryCommentInline]

    fieldsets = (
        (
            'Strategy (Story)',
            {'fields': ('epic', 'name', 'description', 'status')},
        ),
        (
            'Mathematical Lobe',
            {
                'fields': ('vector',),
                'classes': ('collapse',),
            },
        ),
        (
            'System Timestamps',
            {
                'fields': ('created', 'modified', 'delta'),
                'classes': ('collapse',),
            },
        ),
    )

    def task_count(self, obj):
        count = obj.tasks.count()
        return format_html(f'<b>{count}</b>')

    task_count.short_description = 'Tasks'

    def epic_link(self, obj):
        if obj.epic:
            url = reverse(
                'admin:prefrontal_cortex_pfcepic_change', args=[obj.epic.id]
            )
            return format_html(
                f'<a href="{url}" style="font-weight:bold; color:#a855f7;">{obj.epic.name}</a>'
            )
        return '-'

    epic_link.short_description = 'Parent Epic'


@admin.register(PFCTask)
class PFCTaskAdmin(admin.ModelAdmin):
    list_display = ('name', 'story_link', 'status', 'created')
    list_filter = ('status', 'story__epic', 'story')
    search_fields = ('name', 'description', 'story__name', 'story__epic__name')
    readonly_fields = ('created', 'modified', 'delta', 'vector', 'story_link')

    inlines = [TaskCommentInline]

    fieldsets = (
        (
            'Tactic (Task)',
            {'fields': ('story', 'name', 'description', 'status')},
        ),
        (
            'Mathematical Lobe',
            {
                'fields': ('vector',),
                'classes': ('collapse',),
            },
        ),
        (
            'System Timestamps',
            {
                'fields': ('created', 'modified', 'delta'),
                'classes': ('collapse',),
            },
        ),
    )

    def story_link(self, obj):
        if obj.story:
            url = reverse(
                'admin:prefrontal_cortex_pfcstory_change', args=[obj.story.id]
            )
            return format_html(
                f'<a href="{url}" style="font-weight:bold; color:#3b82f6;">{obj.story.name}</a>'
            )
        return '-'

    story_link.short_description = 'Parent Story'


@admin.register(PFCComment)
class CommentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user_display',
        'target_item',
        'text_snippet',
        'created',
    )
    list_filter = ('created', 'user')
    search_fields = ('text', 'user__username')

    def user_display(self, obj):
        if obj.user:
            return obj.user.username
        return format_html(
            '<span style="color: #f99f1b; font-weight: bold;">Talos (System)</span>'
        )

    user_display.short_description = 'Author'

    def target_item(self, obj):
        if obj.epic:
            url = reverse(
                'admin:prefrontal_cortex_pfcepic_change', args=[obj.epic.id]
            )
            return format_html(
                f'<span style="color: #a855f7; font-weight: bold;">Epic:</span> <a href="{url}">{obj.epic.name}</a>'
            )
        if obj.story:
            url = reverse(
                'admin:prefrontal_cortex_pfcstory_change', args=[obj.story.id]
            )
            return format_html(
                f'<span style="color: #3b82f6; font-weight: bold;">Story:</span> <a href="{url}">{obj.story.name}</a>'
            )
        if obj.task:
            url = reverse(
                'admin:prefrontal_cortex_pfctask_change', args=[obj.task.id]
            )
            return format_html(
                f'<span style="color: #4ade80; font-weight: bold;">Task:</span> <a href="{url}">{obj.task.name}</a>'
            )
        return 'Orphaned Comment'

    target_item.short_description = 'Attached To'

    def text_snippet(self, obj):
        return obj.text[:60] + '...' if len(obj.text) > 60 else obj.text

    text_snippet.short_description = 'Comment'
