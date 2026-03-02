"""
Remove migration records from django_migrations for any app (entire or selected).

Also removes the corresponding migration .py files (not the migrations folder
or __init__.py). Use when migration history is inconsistent and you need to
clear an app's records so you can re-run migrate (e.g. migrate <app> zero
--fake). This command does not load the migration graph, so it runs even when
migrate would raise InconsistentMigrationHistory.
"""

import argparse
from pathlib import Path
from typing import Any, List, Optional, Tuple

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder


class Command(BaseCommand):
    """
    Remove migration records for a given app; all or only specified names.

    Uses MigrationRecorder only (no migration loader), so it runs even when
    migrate would raise InconsistentMigrationHistory.
    """

    help = (
        "Remove rows from django_migrations for an app and the corresponding "
        "migration .py files (never the migrations folder or __init__.py). "
        "Pass app_label and optionally migration names (e.g. 0001_initial). "
        "If no names are given, removes all records for that app. Use --all to "
        "clear migrations for every app that has records."
    )

    @staticmethod
    def _migrations_dir_for_app(app_label: str) -> Optional[Path]:
        """Return the migrations directory Path for the app, or None if not found."""
        try:
            app_config = apps.get_app_config(app_label)
        except LookupError:
            return None
        path = Path(app_config.path) / 'migrations'
        return path if path.is_dir() else None

    def _clear_app_migrations(
        self,
        recorder: MigrationRecorder,
        app_label: str,
        to_remove: List[Tuple[str, str]],
        migration_names: List[str],
        dry_run: bool,
    ) -> None:
        """Remove DB records and migration files (except __init__.py) for one app."""
        migrations_dir = self._migrations_dir_for_app(app_label)

        if dry_run:
            self.stdout.write(
                f'Would remove {len(to_remove)} {app_label} record(s):'
            )
            for (_, name) in to_remove:
                self.stdout.write(f'  - {name}')
            if migrations_dir:
                for (_, name) in to_remove:
                    p = migrations_dir / f'{name}.py'
                    self.stdout.write(f'  (file) {p}')
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'App {app_label} or migrations dir not found; no files to remove.'
                    )
                )
            return

        for (app, name) in to_remove:
            recorder.record_unapplied(app, name)

        removed_files: List[Path] = []
        if migrations_dir:
            for (_, name) in to_remove:
                path = migrations_dir / f'{name}.py'
                if path.name == '__init__.py':
                    continue
                if path.is_file():
                    path.unlink()
                    removed_files.append(path)
            if removed_files:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Removed {len(removed_files)} migration file(s).'
                    )
                )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f'App {app_label} or migrations dir not found; only DB records removed.'
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Removed {len(to_remove)} {app_label} migration record(s).'
            )
        )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            'app_label',
            nargs='?',
            type=str,
            default=None,
            help='App label (e.g. talos_hippocampus, frontal_lobe). Required unless --all.',
        )
        parser.add_argument(
            'migrations',
            nargs='*',
            type=str,
            metavar='migration',
            help=(
                'Optional migration names to remove (e.g. 0001_initial). '
                'If omitted, remove all migration records for the app(s).'
            ),
        )
        parser.add_argument(
            '--all',
            action='store_true',
            dest='clear_all',
            help='Clear migration records and files for every app that has records.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Show what would be removed without changing the DB.',
        )

    def handle(self, *args: Any, **options: Any) -> None:
        app_label = options['app_label']
        migration_names: List[str] = options['migrations'] or []
        clear_all = options['clear_all']
        dry_run = options['dry_run']

        if clear_all and app_label:
            raise CommandError('Cannot pass app_label when using --all.')
        if not clear_all and not app_label:
            raise CommandError('app_label required unless --all.')

        recorder = MigrationRecorder(connection)
        recorder.ensure_schema()

        applied = recorder.applied_migrations()

        # Build list of (app_label, to_remove) for each app to process.
        if clear_all:
            apps_with_records = {app for (app, _) in applied}
            per_app: List[Tuple[str, List[Tuple[str, str]]]] = [
                (label, [(a, n) for (a, n) in applied if a == label])
                for label in sorted(apps_with_records)
            ]
        else:
            if migration_names:
                name_set = set(migration_names)
                to_remove: List[Tuple[str, str]] = [
                    (app, name)
                    for (app, name) in applied
                    if app == app_label and name in name_set
                ]
                not_found = name_set - {name for (_, name) in to_remove}
                if not_found:
                    self.stdout.write(
                        self.style.WARNING(
                            f'No recorded migrations named: {', '.join(sorted(not_found))}'
                        )
                    )
            else:
                to_remove = [
                    (app, name) for (app, name) in applied if app == app_label
                ]
            per_app = [(app_label, to_remove)] if to_remove else []

        if not per_app:
            self.stdout.write('No migration records to remove.')
            return

        for label, to_remove in per_app:
            self._clear_app_migrations(
                recorder=recorder,
                app_label=label,
                to_remove=to_remove,
                migration_names=migration_names if not clear_all else [],
                dry_run=dry_run,
            )

