from . import distributor
from . import version_stamper

class NativeExecutables:
    """
    Registry for Python-native spells that run inside the Worker process.
    Maps a DB Slug -> Python Function.
    """
    # Slugs defined in Fixtures
    DISTRIBUTE_FLEET = 'distribute_fleet'
    VERSION_STAMPER = 'version_stamper'

    # Map Slug -> Handler Function
    # Handler signature: def handler(head): -> returns (exit_code, log_output)
    HANDLERS = {
        DISTRIBUTE_FLEET: distributor.distribute_build_native,
        VERSION_STAMPER: version_stamper.version_stamp_native,
    }

    @classmethod
    def get_handler(cls, slug):
        return cls.HANDLERS.get(slug)