from django.contrib import admin
from .models import BuildProfile, PipelineRun

@admin.register(BuildProfile)
class BuildProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'headless', 'staging', 'steam')

@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display = ('id', 'profile', 'status', 'created_at')
    list_filter = ('status', 'profile')
    readonly_fields = ('created_at', 'celery_task_id')
