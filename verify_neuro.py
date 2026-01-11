import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from hydra.models import HydraSpawn, HydraSpellbook, HydraEnvironment, HydraSpawnStatus, HydraHeadStatus, HydraHead, HydraSpell, HydraExecutable
from hydra.hydra import Hydra
from talos_frontal.models import ConsciousStream
from environments.models import ProjectEnvironment


def verify():
    print("Verifying Neuro-Complex...")

    # Setup Data
    exe, _ = HydraExecutable.objects.get_or_create(
        slug='test_exe', defaults={'name': 'Test Exe'})
    spell, _ = HydraSpell.objects.get_or_create(name='Test Spell',
                                                executable=exe,
                                                defaults={'order': 1})
    book, _ = HydraSpellbook.objects.get_or_create(
        name='Test Book', defaults={'description': 'Test'})
    book.spells.add(spell)

    try:
        pe, _ = ProjectEnvironment.objects.get_or_create(
            name='Test Env', defaults={'project_root': 'C:/Test'})
        he, _ = HydraEnvironment.objects.get_or_create(project_environment=pe)

        controller = Hydra(spellbook_id=book.id, env_id=he.id)
        spawn = controller.spawn
        print(f"Created Spawn {spawn.id}")

        # Create a head and set it to failed (skipping start() to avoid real dispatch)
        head = HydraHead.objects.create(spawn=spawn,
                                        spell=spell,
                                        status_id=HydraHeadStatus.FAILED)
        head.spell_log = "[2026-01-11 10:00:00] Verify Log...\nError: Something went wrong.\nException: Bad link.\n[2026-01-11 10:00:01] End."
        head.save()

        # Trigger finalization
        controller._finalize_spawn()

        # Check ConsciousStream
        stream = ConsciousStream.objects.filter(spawn_link=spawn).first()
        if stream:
            print(f"[SUCCESS] ConsciousStream created: {stream}")
            print(f"Thought: {stream.current_thought}")
        else:
            print("[FAILURE] No ConsciousStream found.")

    except Exception as e:
        print(f"[ERROR] Verification failed: {e}")


if __name__ == "__main__":
    verify()
