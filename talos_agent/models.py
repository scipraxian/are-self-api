'''Models for the Talos Agent application, tracking remote agent telemetry.'''

import uuid
from django.db import models
from core.models import RemoteTarget

class AgentTelemetry(models.Model):
  '''Stores periodic snapshots of agent health and performance.'''
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  target = models.ForeignKey(RemoteTarget, on_delete=models.CASCADE, related_name='telemetry')
  timestamp = models.DateTimeField(auto_now_add=True)
  
  cpu_usage = models.FloatField(default=0.0)
  memory_usage_mb = models.FloatField(default=0.0)
  is_functioning = models.BooleanField(default=False)
  is_alive = models.BooleanField(default=False)
  storage_ok = models.BooleanField(default=False)
  storage_info = models.CharField(max_length=500, blank=True)
  
  raw_payload = models.JSONField(null=True, blank=True)

  class Meta:
    ordering = ['-timestamp']
    verbose_name_plural = 'Agent Telemetry'

  def __str__(self):
    return f'{self.target.hostname} @ {self.timestamp}'

class AgentEvent(models.Model):
  '''Records significant lifecycle events for an agent.'''
  EVENT_TYPES = [
      ('LAUNCH', 'Started Process'),
      ('KILL', 'Stopped Process'),
      ('CRASH', 'Detected Crash'),
      ('DISCONNECT', 'Lost Connection'),
      ('RECONNECT', 'Restored Connection'),
      ('UPDATE', 'Agent Code Updated'),
  ]

  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  target = models.ForeignKey(RemoteTarget, on_delete=models.CASCADE, related_name='events')
  timestamp = models.DateTimeField(auto_now_add=True)
  event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
  message = models.TextField(blank=True)
  
  class Meta:
    ordering = ['-timestamp']

  def __str__(self):
    return f'{self.event_type} on {self.target.hostname}'
