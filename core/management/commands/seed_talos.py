import os
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db.utils import IntegrityError


class Command(BaseCommand):
    help = 'Dynamically finds and seeds ALL fixtures in the project, resolving dependencies automatically.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('--- TALOS DYNAMIC GENESIS ---'))

        base_dir = Path(settings.BASE_DIR)
        fixtures = []

        # 1. DISCOVERY (The Scan)
        self.stdout.write(f"Scanning {base_dir} for fixtures...")

        # Walk the tree looking for */fixtures/*.json
        for root, dirs, files in os.walk(base_dir):
            if 'fixtures' in dirs:
                fixture_path = Path(root) / 'fixtures'
                for f in os.listdir(fixture_path):
                    if f.endswith('.json'):
                        full_path = fixture_path / f
                        # Store relative path for cleaner output/loaddata
                        rel_path = full_path.relative_to(base_dir)
                        fixtures.append(str(full_path))

        self.stdout.write(f"Found {len(fixtures)} fixture files.\n")

        # 2. THE RESOLUTION LOOP
        # We don't know the order, so we loop until all are loaded or we get stuck.
        pending = fixtures[:]
        max_passes = 5
        current_pass = 1

        while pending and current_pass <= max_passes:
            self.stdout.write(self.style.WARNING(f'--- Pass {current_pass} (Pending: {len(pending)}) ---'))

            # Track progress to avoid infinite loops
            successful_this_pass = []

            for fixture in pending:
                try:
                    # Attempt load
                    call_command('loaddata', fixture, verbosity=0)
                    self.stdout.write(f"  [OK]   {os.path.basename(fixture)}")
                    successful_this_pass.append(fixture)
                except IntegrityError:
                    # Dependency missing (e.g. tried to load Hydra before Environment)
                    self.stdout.write(f"  [WAIT] {os.path.basename(fixture)} (Dependency missing)")
                except Exception as e:
                    # Genuine error (Syntax, bad field) - Report and Drop
                    self.stdout.write(self.style.ERROR(f"  [FAIL] {os.path.basename(fixture)}: {e}"))
                    # We remove it from pending so we don't retry forever on a syntax error
                    successful_this_pass.append(fixture)

                    # Remove successes from the queue
            for s in successful_this_pass:
                pending.remove(s)

            if not successful_this_pass and pending:
                self.stdout.write(
                    self.style.ERROR("\n[FATAL] Deadlock detected. Remaining fixtures satisfy no dependencies."))
                for p in pending:
                    self.stdout.write(f" - {p}")
                break

            current_pass += 1

        if not pending:
            self.stdout.write(self.style.SUCCESS('\n>>> ALL SYSTEMS ONLINE. DATABASE SEEDED.'))
        else:
            self.stdout.write(self.style.ERROR('\n>>> SEEDING INCOMPLETE.'))