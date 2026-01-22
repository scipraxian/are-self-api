# TODO: update outcomes to new pattern


# from django.test import TestCase


# from hydra.models import HydraHead, HydraSpawn, HydraSpell, HydraExecutable, HydraSpellOutcomeConfig, HydraOutcomeAction, HydraOutcomeActionID, HydraSpellbook, HydraEnvironment, HydraSpawnStatus, HydraHeadStatus
# from hydra.spells.spell_casters.outcomes import process_outcomes
# from environments.models import ProjectEnvironment
# import tempfile
# import shutil
# import os
#
#
# class OutcomesTestCase(TestCase):
#     fixtures = [
#         'talos_frontal/fixtures/initial_data.json',
#         'hydra/fixtures/initial_data.json',
#         'environments/fixtures/initial_data.json',
#         'talos_reasoning/fixtures/initial_data.json'
#     ]
#     def setUp(self):
#         # Create temp dirs
#         self.test_dir = tempfile.mkdtemp()
#         self.project_root = os.path.join(self.test_dir, "Project")
#         self.engine_root = os.path.join(self.test_dir, "Engine")
#         self.build_root = os.path.join(self.test_dir, "Build")
#         self.staging_dir = os.path.join(self.test_dir, "Saved", "Staging")
#
#         os.makedirs(self.project_root)
#         os.makedirs(self.staging_dir)
#         os.makedirs(self.build_root)
#
#         # Setup DB
#         self.proj_env = ProjectEnvironment.objects.create(
#             name="TestEnv",
#             project_root=self.project_root,
#             engine_root=self.engine_root,
#             build_root=self.build_root,
#             staging_dir=self.staging_dir,
#             project_name="TestProject")
#
#         self.env = HydraEnvironment.objects.create(
#             project_environment=self.proj_env)
#
#         self.exe = HydraExecutable.objects.create(name="TestExe",
#                                                   slug="test_exe",
#                                                   path_template="echo")
#         self.spell = HydraSpell.objects.create(name="TestSpell",
#                                                executable=self.exe,
#                                                order=1)
#         self.spellbook = HydraSpellbook.objects.create(name="TestBook")
#
#         # Create Statuses if they don't exist (handle unique constraint if pre-populated)
#         for sid, name in [(1, "Created"), (2, "Pending"), (3, "Running"),
#                           (4, "Success"), (5, "Failed")]:
#             HydraHeadStatus.objects.get_or_create(id=sid,
#                                                   defaults={'name': name})
#             HydraSpawnStatus.objects.get_or_create(id=sid,
#                                                    defaults={'name': name})
#
#         # Create Outcome Actions
#         HydraOutcomeAction.objects.get_or_create(id=HydraOutcomeActionID.COPY,
#                                                  defaults={'name': "Copy"})
#         HydraOutcomeAction.objects.get_or_create(id=HydraOutcomeActionID.MOVE,
#                                                  defaults={'name': "Move"})
#         HydraOutcomeAction.objects.get_or_create(
#             id=HydraOutcomeActionID.VALIDATE_EXISTS,
#             defaults={'name': "Validate"})
#         HydraOutcomeAction.objects.get_or_create(id=HydraOutcomeActionID.DELETE,
#                                                  defaults={'name': "Delete"})
#
#         self.status_success = HydraHeadStatus.objects.get(
#             id=HydraHeadStatus.SUCCESS)
#         self.spawn_status = HydraSpawnStatus.objects.get(
#             id=HydraSpawnStatus.PENDING)
#
#         self.spawn = HydraSpawn.objects.create(spellbook=self.spellbook,
#                                                environment=self.env,
#                                                status=self.spawn_status)
#
#         self.head = HydraHead.objects.create(spawn=self.spawn,
#                                              spell=self.spell,
#                                              status=self.status_success)
#
#     def tearDown(self):
#         try:
#             shutil.rmtree(self.test_dir)
#         except:
#             pass
#
#     def test_outcome_move(self):
#         # Create source file
#         src_file = os.path.join(self.staging_dir, "test_artifact.txt")
#         with open(src_file, "w") as f:
#             f.write("content")
#
#         # Config outcome
#         outcome = HydraSpellOutcomeConfig.objects.create(
#             spell=self.spell,
#             action_id=HydraOutcomeActionID.MOVE,
#             source_path_template="{staging_dir}/test_artifact.txt",
#             dest_path_template="{build_root}/Moved/",
#             must_exist=True)
#
#         process_outcomes(self.head.id)
#
#         # Verify
#         dest_file = os.path.join(self.build_root, "Moved", "test_artifact.txt")
#         self.assertTrue(os.path.exists(dest_file),
#                         "Destination file should exist")
#         self.assertFalse(os.path.exists(src_file), "Source file should be gone")
#
#         self.head.refresh_from_db()
#         self.assertEqual(self.head.status_id, HydraHeadStatus.SUCCESS)
#
#     def test_outcome_glob_copy(self):
#         # Create multiple files
#         log_dir = os.path.join(self.staging_dir, "logs")
#         os.makedirs(log_dir)
#         with open(os.path.join(log_dir, "a.log"), "w") as f:
#             f.write("a")
#         with open(os.path.join(log_dir, "b.log"), "w") as f:
#             f.write("b")
#
#         outcome = HydraSpellOutcomeConfig.objects.create(
#             spell=self.spell,
#             action_id=HydraOutcomeActionID.COPY,
#             source_path_template="{staging_dir}/logs/*.log",
#             dest_path_template="{build_root}/Logs/",
#             must_exist=True)
#
#         process_outcomes(self.head.id)
#
#         self.assertTrue(
#             os.path.exists(os.path.join(self.build_root, "Logs", "a.log")))
#         self.assertTrue(
#             os.path.exists(os.path.join(self.build_root, "Logs", "b.log")))
#         # Source should still exist
#         self.assertTrue(os.path.exists(os.path.join(log_dir, "a.log")))
#
#     def test_outcome_failure_missing(self):
#         outcome = HydraSpellOutcomeConfig.objects.create(
#             spell=self.spell,
#             action_id=HydraOutcomeActionID.COPY,
#             source_path_template="{staging_dir}/missing.txt",
#             dest_path_template="{build_root}/",
#             must_exist=True)
#
#         process_outcomes(self.head.id)
#
#         self.head.refresh_from_db()
#         self.assertEqual(self.head.status_id, HydraHeadStatus.FAILED)
#         self.assertIn("Source pattern matched nothing", self.head.execution_log)
