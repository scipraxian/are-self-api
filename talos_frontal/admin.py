from django.contrib import admin
from .models import ConsciousStream


@admin.register(ConsciousStream)
class ConsciousStreamAdmin(admin.ModelAdmin):
    list_display = ('id', 'spawn_link', 'status', 'created')
    readonly_fields = ('created', 'modified')
    list_filter = ('status',)
