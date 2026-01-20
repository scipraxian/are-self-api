from . import distributor, local_execution, remote_execution, version_stamper  # <--- IMPORT NEW MODULE


class NativeExecutables:
    """
    Registry for Python-native spells that run inside the Worker process.
    Maps a DB Slug -> Python Function.

    # Map Slug -> Handler Function
    # Handler signature: def handler(head): -> returns (exit_code, log_output)

    """
    # Slugs defined in Fixtures
    DISTRIBUTE_FLEET = 'distribute_fleet'
    NATIVE_LOCAL_CLIENT = 'native_local_client'
    REMOTE_LAUNCH = 'remote_launch'
    VERSION_STAMPER = 'version_stamper'

    HANDLERS = {
        DISTRIBUTE_FLEET: distributor.distribute_build_native,
        NATIVE_LOCAL_CLIENT: local_execution.local_launch_native,
        REMOTE_LAUNCH: remote_execution.remote_launch_native,
        VERSION_STAMPER: version_stamper.version_stamp_native,
    }

    @classmethod
    def get_handler(cls, slug):
        return cls.HANDLERS.get(slug)