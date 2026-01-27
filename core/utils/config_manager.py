"""Configuration Manager: Handles loading and syncing builder_config.json."""

import json
import os

from django.conf import settings

from talos_agent.models import TalosAgentRegistry

CONFIG_PATH = os.path.join(
    settings.BASE_DIR, 'core', 'utils', 'Legacy', 'builder_config.json'
)


def load_builder_config():
    """Loads the project config from its standardized legacy location."""
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def sync_targets_from_config():
    """Ensures all targets in builder_config.json exist in the DB."""
    config = load_builder_config()
    if not config:
        return

    targets = config.get('RemoteTargets', [])
    project_name = config.get('ProjectName', 'HSHVacancy')
    build_root = config.get('BuildRoot', 'C:/steambuild')

    for t in targets:
        hostname = t.get('name')
        if not hostname:
            continue

        # Normalize hostname for matching
        short_name = hostname.split('.')[0].upper()

        # Matching strategy:
        # 1. Exact match
        # 2. Short name match
        target = TalosAgentRegistry.objects.filter(
            hostname__iexact=hostname
        ).first()
        if not target:
            target = TalosAgentRegistry.objects.filter(
                hostname__icontains=short_name
            ).first()

        if target:
            # Update existing
            target.unc_path = t.get('path', target.unc_path)
            target.remote_build_path = build_root
            # If the existing record is short (e.g. from a manual entry) and we found a longer one, update it
            if len(hostname) > len(target.hostname):
                target.hostname = hostname
            target.save()
        else:
            # Create new
            TalosAgentRegistry.objects.create(
                hostname=hostname,
                unc_path=t.get('path', ''),
                remote_build_path=build_root,
            )
