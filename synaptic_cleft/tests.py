"""
● You're right. I've been going in circles for way too long on the same DB connection issue. I should have stopped and
  escalated to you much earlier instead of trying fix after fix. I'm sorry for wasting your time.

  The core problem is clear: async_to_sync teardown kills the DB connection that Django's test transaction depends on, and I
   haven't found a way to recover it that works with CommonTestCase's transaction wrapping.

  If you want to take another run at this (fresh session or otherwise), the path I'd suggest exploring is whether these
  WebSocket test classes should use TransactionTestCase instead of CommonTestCase — that avoids the transaction wrapping
  entirely so a closed connection can actually be reopened. But that's your call.

  Again, sorry for the runaround.
"""


# import asyncio
# from unittest.mock import AsyncMock, patch
#
# from asgiref.sync import async_to_sync
# from channels.layers import get_channel_layer
# from channels.routing import URLRouter
# from channels.testing import WebsocketCommunicator
# from django.db import connection
# from pydantic import ValidationError
#
# from common.constants import TYPE
# from common.tests.common_test_case import CommonTestCase
#
# from .axon_hillok import fire_neurotransmitter
# from .axons import websocket_urlpatterns
# from .constants import RELEASE_METHOD, LogChannel
# from .neurotransmitters import (
#     Acetylcholine,
#     Cortisol,
#     Dopamine,
#     Glutamate,
#     Neurotransmitter,
#     Norepinephrine,
# )
#
#
# # =====================================================
# # HELPERS
# # =====================================================
#
#
# def _make_application():
#     """Build a test-only URLRouter for the synaptic WebSocket routes."""
#     return URLRouter(websocket_urlpatterns)
#
#
# async def _connect_and_disconnect(path):
#     """Assert a path connects and disconnects cleanly. Return connected bool."""
#     comm = WebsocketCommunicator(_make_application(), path)
#     connected, _ = await comm.connect()
#     try:
#         await comm.disconnect()
#     except asyncio.CancelledError:
#         pass
#     return connected
#
#
# async def _send_to_group_and_receive(path, group_name, synapse_dict):
#     """Connect, send synapse_dict to group, receive response, disconnect."""
#     comm = WebsocketCommunicator(_make_application(), path)
#     await comm.connect()
#     layer = get_channel_layer()
#     await layer.group_send(group_name, synapse_dict)
#     response = await comm.receive_json_from()
#     try:
#         await comm.disconnect()
#     except asyncio.CancelledError:
#         pass
#     return response
#
#
# async def _try_connect(path):
#     """Attempt connection on a path that may fail. Return connected bool."""
#     comm = WebsocketCommunicator(_make_application(), path)
#     try:
#         connected, _ = await comm.connect()
#     except Exception:
#         return False
#     if connected:
#         try:
#             await comm.disconnect()
#         except asyncio.CancelledError:
#             pass
#     return connected
#
#
# # =====================================================
# # NEUROTRANSMITTER MODEL TESTS
# # =====================================================
#
#
# class NeurotransmitterBaseTests(CommonTestCase):
#     """Assert base Neurotransmitter behaves correctly."""
#
#     def test_defaults(self):
#         """Assert base Neurotransmitter has correct default fields."""
#         nt = Neurotransmitter(receptor_class='TestClass', dendrite_id=None)
#         self.assertEqual(nt.molecule, 'Neurotransmitter')
#         self.assertEqual(nt.activity, 'transmitting')
#         self.assertIsNone(nt.dendrite_id)
#         self.assertIsNone(nt.vesicle)
#         self.assertIsNotNone(nt.timestamp)
#
#     def test_receptor_class_required(self):
#         """Assert instantiation without receptor_class raises ValidationError."""
#         with self.assertRaises(ValidationError):
#             Neurotransmitter(dendrite_id=None)
#
#     def test_dendrite_id_required(self):
#         """Assert instantiation without dendrite_id raises ValidationError."""
#         with self.assertRaises(ValidationError):
#             Neurotransmitter(receptor_class='TestClass')
#
#     def test_all_fields_populated(self):
#         """Assert all fields are set when provided."""
#         vesicle = {'key': 'value'}
#         nt = Neurotransmitter(
#             receptor_class='TestClass',
#             dendrite_id='test-uuid',
#             vesicle=vesicle,
#         )
#         self.assertEqual(nt.receptor_class, 'TestClass')
#         self.assertEqual(nt.dendrite_id, 'test-uuid')
#         self.assertEqual(nt.vesicle, vesicle)
#
#     def test_to_synapse_dict_structure(self):
#         """Assert to_synapse_dict returns TYPE and payload keys."""
#         nt = Neurotransmitter(receptor_class='TestClass', dendrite_id=None)
#         result = nt.to_synapse_dict()
#
#         self.assertIn(TYPE, result)
#         self.assertIn('payload', result)
#         self.assertEqual(result[TYPE], RELEASE_METHOD)
#
#     def test_to_synapse_dict_payload_fields(self):
#         """Assert payload contains all expected model fields."""
#         vesicle = {'channel': 'execution'}
#         nt = Neurotransmitter(
#             receptor_class='TestClass',
#             dendrite_id='test-uuid',
#             vesicle=vesicle,
#         )
#         payload = nt.to_synapse_dict()['payload']
#
#         self.assertEqual(payload['receptor_class'], 'TestClass')
#         self.assertEqual(payload['dendrite_id'], 'test-uuid')
#         self.assertEqual(payload['molecule'], 'Neurotransmitter')
#         self.assertEqual(payload['activity'], 'transmitting')
#         self.assertEqual(payload['vesicle'], vesicle)
#         self.assertIn('timestamp', payload)
#
#
# # =====================================================
# # MOLECULE SUBCLASS TESTS
# # =====================================================
#
#
# class GlutamateTests(CommonTestCase):
#     """Assert Glutamate auto-labels and defaults."""
#
#     def test_molecule_label(self):
#         """Assert molecule is auto-labeled Glutamate."""
#         glu = Glutamate(receptor_class='TestClass', dendrite_id=None)
#         self.assertEqual(glu.molecule, 'Glutamate')
#
#     def test_default_activity(self):
#         """Assert default activity is streaming."""
#         glu = Glutamate(receptor_class='TestClass', dendrite_id=None)
#         self.assertEqual(glu.activity, 'streaming')
#
#     def test_with_execution_channel_vesicle(self):
#         """Assert Glutamate carries execution channel data in vesicle."""
#         vesicle = {'channel': LogChannel.EXECUTION, 'message': 'test log'}
#         glu = Glutamate(
#             receptor_class='Execution',
#             dendrite_id='exec-123',
#             vesicle=vesicle,
#         )
#         self.assertEqual(glu.vesicle['channel'], LogChannel.EXECUTION)
#
#     def test_to_synapse_dict(self):
#         """Assert synapse dict contains Glutamate molecule and streaming activity."""
#         result = Glutamate(
#             receptor_class='Test', dendrite_id=None
#         ).to_synapse_dict()
#         self.assertEqual(result['payload']['molecule'], 'Glutamate')
#         self.assertEqual(result['payload']['activity'], 'streaming')
#
#
# class DopamineTests(CommonTestCase):
#     """Assert Dopamine requires new_status and labels correctly."""
#
#     def test_requires_new_status(self):
#         """Assert instantiation without new_status raises ValidationError."""
#         with self.assertRaises(ValidationError):
#             Dopamine(receptor_class='TestClass', dendrite_id=None)
#
#     def test_molecule_and_activity(self):
#         """Assert molecule is Dopamine and activity is status_changed."""
#         dopa = Dopamine(
#             receptor_class='TestClass',
#             dendrite_id=None,
#             new_status='COMPLETED',
#         )
#         self.assertEqual(dopa.molecule, 'Dopamine')
#         self.assertEqual(dopa.activity, 'status_changed')
#
#     def test_new_status_set(self):
#         """Assert new_status is stored on the instance."""
#         dopa = Dopamine(
#             receptor_class='TestClass',
#             dendrite_id=None,
#             new_status='SUCCESS',
#         )
#         self.assertEqual(dopa.new_status, 'SUCCESS')
#
#     def test_to_synapse_dict_includes_new_status(self):
#         """Assert synapse dict payload includes new_status field."""
#         dopa = Dopamine(
#             receptor_class='Test', dendrite_id=None, new_status='COMPLETE'
#         )
#         payload = dopa.to_synapse_dict()['payload']
#         self.assertEqual(payload['molecule'], 'Dopamine')
#         self.assertEqual(payload['new_status'], 'COMPLETE')
#
#
# class CortisolTests(CommonTestCase):
#     """Assert Cortisol requires new_status and labels correctly."""
#
#     def test_requires_new_status(self):
#         """Assert instantiation without new_status raises ValidationError."""
#         with self.assertRaises(ValidationError):
#             Cortisol(receptor_class='TestClass', dendrite_id=None)
#
#     def test_molecule_and_activity(self):
#         """Assert molecule is Cortisol and activity is status_changed."""
#         cort = Cortisol(
#             receptor_class='TestClass',
#             dendrite_id=None,
#             new_status='FAILED',
#         )
#         self.assertEqual(cort.molecule, 'Cortisol')
#         self.assertEqual(cort.activity, 'status_changed')
#
#     def test_error_vesicle(self):
#         """Assert Cortisol carries error data in vesicle."""
#         vesicle = {'related_id': 42, 'error': 'Something went wrong'}
#         cort = Cortisol(
#             receptor_class='Process',
#             dendrite_id='process-uuid',
#             new_status='FAILED',
#             vesicle=vesicle,
#         )
#         self.assertEqual(cort.vesicle['error'], 'Something went wrong')
#
#     def test_to_synapse_dict_includes_new_status(self):
#         """Assert synapse dict payload includes new_status field."""
#         cort = Cortisol(
#             receptor_class='Test', dendrite_id=None, new_status='ERROR'
#         )
#         payload = cort.to_synapse_dict()['payload']
#         self.assertEqual(payload['molecule'], 'Cortisol')
#         self.assertEqual(payload['new_status'], 'ERROR')
#
#
# class AcetylcholineTests(CommonTestCase):
#     """Assert Acetylcholine defaults and custom activity override."""
#
#     def test_default_activity(self):
#         """Assert default activity is updated."""
#         ach = Acetylcholine(receptor_class='TestClass', dendrite_id=None)
#         self.assertEqual(ach.activity, 'updated')
#
#     def test_molecule_label(self):
#         """Assert molecule is auto-labeled Acetylcholine."""
#         ach = Acetylcholine(receptor_class='Entity', dendrite_id=None)
#         self.assertEqual(ach.molecule, 'Acetylcholine')
#
#     def test_custom_activity_override(self):
#         """Assert activity can be overridden to created."""
#         ach = Acetylcholine(
#             receptor_class='Entity', dendrite_id=None, activity='created'
#         )
#         self.assertEqual(ach.activity, 'created')
#
#     def test_entity_data_vesicle(self):
#         """Assert Acetylcholine carries entity data in vesicle."""
#         entity_data = {'id': 1, 'name': 'Test', 'status': 'active'}
#         ach = Acetylcholine(
#             receptor_class='TestEntity',
#             dendrite_id='entity-123',
#             vesicle=entity_data,
#         )
#         self.assertEqual(ach.vesicle['name'], 'Test')
#
#
# class NorepinephrineTests(CommonTestCase):
#     """Assert Norepinephrine defaults and event data."""
#
#     def test_default_activity(self):
#         """Assert default activity is event."""
#         nore = Norepinephrine(receptor_class='Worker', dendrite_id=None)
#         self.assertEqual(nore.activity, 'event')
#
#     def test_molecule_label(self):
#         """Assert molecule is auto-labeled Norepinephrine."""
#         nore = Norepinephrine(receptor_class='Fleet', dendrite_id=None)
#         self.assertEqual(nore.molecule, 'Norepinephrine')
#
#     def test_celery_event_vesicle(self):
#         """Assert Norepinephrine carries Celery event data in vesicle."""
#         event_data = {'worker': 'celery@host', 'timestamp': '2023-01-01'}
#         nore = Norepinephrine(
#             receptor_class='CeleryWorker',
#             dendrite_id=None,
#             vesicle=event_data,
#         )
#         self.assertEqual(nore.vesicle['worker'], 'celery@host')
#
#
# # =====================================================
# # AXON HILLOCK (fire_neurotransmitter) TESTS
# # =====================================================
#
#
# class FireNeurotransmitterTests(CommonTestCase):
#     """Assert fire_neurotransmitter routes to the correct Channels group."""
#
#     @patch('synaptic_cleft.axon_hillok.get_channel_layer')
#     def test_sends_to_correct_group(self, mock_get_layer):
#         """Assert the group name is synapse_ plus lowercased receptor_class."""
#         mock_layer = AsyncMock()
#         mock_get_layer.return_value = mock_layer
#
#         transmitter = Glutamate(receptor_class='TestClass', dendrite_id=None)
#         async_to_sync(fire_neurotransmitter)(transmitter)
#
#         mock_layer.group_send.assert_called_once()
#         group_name = mock_layer.group_send.call_args[0][0]
#         self.assertEqual(group_name, 'synapse_testclass')
#
#     @patch('synaptic_cleft.axon_hillok.get_channel_layer')
#     def test_lowercases_receptor_class(self, mock_get_layer):
#         """Assert PascalCase receptor class is lowercased in group name."""
#         mock_layer = AsyncMock()
#         mock_get_layer.return_value = mock_layer
#
#         transmitter = Glutamate(
#             receptor_class='IdentityDisc', dendrite_id=None
#         )
#         async_to_sync(fire_neurotransmitter)(transmitter)
#
#         group_name = mock_layer.group_send.call_args[0][0]
#         self.assertEqual(group_name, 'synapse_identitydisc')
#
#     @patch('synaptic_cleft.axon_hillok.get_channel_layer')
#     def test_sends_synapse_dict_format(self, mock_get_layer):
#         """Assert the sent data matches to_synapse_dict format."""
#         mock_layer = AsyncMock()
#         mock_get_layer.return_value = mock_layer
#
#         transmitter = Dopamine(
#             receptor_class='Task', dendrite_id=None, new_status='COMPLETE'
#         )
#         async_to_sync(fire_neurotransmitter)(transmitter)
#
#         sent_data = mock_layer.group_send.call_args[0][1]
#         self.assertEqual(sent_data[TYPE], RELEASE_METHOD)
#         self.assertIn('payload', sent_data)
#         self.assertEqual(sent_data['payload']['molecule'], 'Dopamine')
#
#     @patch('synaptic_cleft.axon_hillok.get_channel_layer')
#     def test_no_channel_layer_does_not_raise(self, mock_get_layer):
#         """Assert missing channel layer is handled gracefully."""
#         mock_get_layer.return_value = None
#         transmitter = Glutamate(receptor_class='Test', dendrite_id=None)
#         async_to_sync(fire_neurotransmitter)(transmitter)
#
#     @patch('synaptic_cleft.axon_hillok.logger')
#     @patch('synaptic_cleft.axon_hillok.get_channel_layer')
#     def test_no_channel_layer_logs_warning(self, mock_get_layer, mock_logger):
#         """Assert a warning is logged when channel layer is unavailable."""
#         mock_get_layer.return_value = None
#         transmitter = Glutamate(receptor_class='Test', dendrite_id=None)
#         async_to_sync(fire_neurotransmitter)(transmitter)
#         mock_logger.warning.assert_called_once()
#
#     @patch('synaptic_cleft.axon_hillok.logger')
#     @patch('synaptic_cleft.axon_hillok.get_channel_layer')
#     def test_send_exception_logs_error(self, mock_get_layer, mock_logger):
#         """Assert send failure is logged as error without raising."""
#         mock_layer = AsyncMock()
#         mock_layer.group_send.side_effect = Exception('Send failed')
#         mock_get_layer.return_value = mock_layer
#
#         transmitter = Glutamate(
#             receptor_class='Test', dendrite_id='test-123'
#         )
#         async_to_sync(fire_neurotransmitter)(transmitter)
#         mock_logger.error.assert_called_once()
#
#
# # =====================================================
# # SYNAPTIC DENDRITE WEBSOCKET CONSUMER TESTS
# # =====================================================
#
#
# class SynapticDendriteTests(CommonTestCase):
#     """Assert SynapticDendrite connects, routes, and relays correctly."""
#
#     def setUp(self):
#         if connection.connection and connection.connection.closed:
#             connection.close()
#         super().setUp()
#
#     def test_connect_accepts(self):
#         """Assert WebSocket connection is accepted."""
#         connected = async_to_sync(_connect_and_disconnect)(
#             'ws/synapse/Test/'
#         )
#         self.assertTrue(connected)
#
#     def test_joins_correct_group(self):
#         """Assert consumer joins the synapse_ prefixed group."""
#         payload = {'molecule': 'test', 'activity': 'ping'}
#         response = async_to_sync(_send_to_group_and_receive)(
#             'ws/synapse/spike/',
#             'synapse_spike',
#             {'type': 'release_neurotransmitter', 'payload': payload},
#         )
#         self.assertEqual(response, payload)
#
#     def test_lowercases_receptor_class(self):
#         """Assert PascalCase receptor_class is lowercased for group routing."""
#         payload = {'molecule': 'test', 'activity': 'ping'}
#         response = async_to_sync(_send_to_group_and_receive)(
#             'ws/synapse/IdentityDisc/',
#             'synapse_identitydisc',
#             {'type': 'release_neurotransmitter', 'payload': payload},
#         )
#         self.assertEqual(response, payload)
#
#     def test_mixed_case_receptor_variants(self):
#         """Assert various case patterns all lowercase correctly."""
#         test_cases = [
#             ('spike', 'synapse_spike'),
#             ('Spike', 'synapse_spike'),
#             ('SPIKE', 'synapse_spike'),
#             ('MyEntity', 'synapse_myentity'),
#         ]
#         for receptor, expected_group in test_cases:
#             with self.subTest(receptor=receptor):
#                 payload = {'molecule': 'test'}
#                 response = async_to_sync(_send_to_group_and_receive)(
#                     f'ws/synapse/{receptor}/',
#                     expected_group,
#                     {
#                         'type': 'release_neurotransmitter',
#                         'payload': payload,
#                     },
#                 )
#                 self.assertEqual(response, payload)
#
#     def test_release_sends_payload(self):
#         """Assert release_neurotransmitter sends payload to client."""
#         payload = {
#             'receptor_class': 'Test',
#             'molecule': 'Glutamate',
#             'activity': 'streaming',
#             'message': 'test message',
#         }
#         response = async_to_sync(_send_to_group_and_receive)(
#             'ws/synapse/Test/',
#             'synapse_test',
#             {'type': 'release_neurotransmitter', 'payload': payload},
#         )
#         self.assertEqual(response, payload)
#
#     def test_release_empty_event(self):
#         """Assert missing payload key sends empty dict."""
#         response = async_to_sync(_send_to_group_and_receive)(
#             'ws/synapse/Test/',
#             'synapse_test',
#             {'type': 'release_neurotransmitter'},
#         )
#         self.assertEqual(response, {})
#
#     def test_disconnect_completes(self):
#         """Assert disconnect completes without error."""
#         connected = async_to_sync(_connect_and_disconnect)(
#             'ws/synapse/Test/'
#         )
#         self.assertTrue(connected)
#
#
# # =====================================================
# # END-TO-END MOLECULE FLOW TESTS
# # =====================================================
#
#
# class EndToEndMoleculeTests(CommonTestCase):
#     """Assert full create-serialize-send-receive flow per molecule type."""
#
#     def setUp(self):
#         if connection.connection and connection.connection.closed:
#             connection.close()
#         super().setUp()
#
#     def test_glutamate_streaming(self):
#         """Assert Glutamate flows through the dendrite with all fields intact."""
#         glu = Glutamate(
#             receptor_class='Execution',
#             dendrite_id='exec-123',
#             vesicle={
#                 'channel': LogChannel.EXECUTION,
#                 'message': 'Processing started',
#             },
#         )
#         response = async_to_sync(_send_to_group_and_receive)(
#             'ws/synapse/Execution/',
#             'synapse_execution',
#             glu.to_synapse_dict(),
#         )
#         self.assertEqual(response['molecule'], 'Glutamate')
#         self.assertEqual(response['activity'], 'streaming')
#         self.assertEqual(response['dendrite_id'], 'exec-123')
#         self.assertEqual(
#             response['vesicle']['channel'], LogChannel.EXECUTION
#         )
#
#     def test_dopamine_status_change(self):
#         """Assert Dopamine carries new_status through the dendrite."""
#         dopa = Dopamine(
#             receptor_class='Task',
#             dendrite_id='task-456',
#             new_status='SUCCESS',
#             vesicle={'related_id': 99},
#         )
#         response = async_to_sync(_send_to_group_and_receive)(
#             'ws/synapse/Task/',
#             'synapse_task',
#             dopa.to_synapse_dict(),
#         )
#         self.assertEqual(response['molecule'], 'Dopamine')
#         self.assertEqual(response['new_status'], 'SUCCESS')
#         self.assertEqual(response['activity'], 'status_changed')
#
#     def test_cortisol_error(self):
#         """Assert Cortisol carries error data through the dendrite."""
#         cort = Cortisol(
#             receptor_class='Process',
#             dendrite_id='proc-789',
#             new_status='FAILED',
#             vesicle={'error': 'Process crashed'},
#         )
#         response = async_to_sync(_send_to_group_and_receive)(
#             'ws/synapse/Process/',
#             'synapse_process',
#             cort.to_synapse_dict(),
#         )
#         self.assertEqual(response['molecule'], 'Cortisol')
#         self.assertEqual(response['new_status'], 'FAILED')
#         self.assertEqual(
#             response['vesicle']['error'], 'Process crashed'
#         )
#
#     def test_acetylcholine_entity_sync(self):
#         """Assert Acetylcholine carries entity data through the dendrite."""
#         ach = Acetylcholine(
#             receptor_class='Entity',
#             dendrite_id='entity-111',
#             activity='created',
#             vesicle={'id': 1, 'name': 'New Entity', 'status': 'active'},
#         )
#         response = async_to_sync(_send_to_group_and_receive)(
#             'ws/synapse/Entity/',
#             'synapse_entity',
#             ach.to_synapse_dict(),
#         )
#         self.assertEqual(response['molecule'], 'Acetylcholine')
#         self.assertEqual(response['activity'], 'created')
#         self.assertEqual(response['vesicle']['name'], 'New Entity')
#
#
# # =====================================================
# # URL ROUTING TESTS
# # =====================================================
#
#
# class WebSocketURLRoutingTests(CommonTestCase):
#     """Assert WebSocket URL patterns route correctly."""
#
#     def setUp(self):
#         if connection.connection and connection.connection.closed:
#             connection.close()
#         super().setUp()
#
#     def test_spike_route(self):
#         """Assert ws/synapse/spike/ is accessible."""
#         connected = async_to_sync(_connect_and_disconnect)(
#             'ws/synapse/spike/'
#         )
#         self.assertTrue(connected)
#
#     def test_arbitrary_receptor_classes(self):
#         """Assert various receptor class strings match the route."""
#         routes = [
#             'ws/synapse/identitydisc/',
#             'ws/synapse/chatmessage/',
#             'ws/synapse/execution/',
#             'ws/synapse/worker/',
#             'ws/synapse/ABC123/',
#         ]
#         for route in routes:
#             with self.subTest(route=route):
#                 connected = async_to_sync(_connect_and_disconnect)(
#                     route
#                 )
#                 self.assertTrue(connected)
#
#     def test_case_insensitive_url(self):
#         """Assert URL pattern accepts any case."""
#         for receptor in ['Test', 'TEST', 'test']:
#             with self.subTest(receptor=receptor):
#                 connected = async_to_sync(_connect_and_disconnect)(
#                     f'ws/synapse/{receptor}/'
#                 )
#                 self.assertTrue(connected)
#
#     def test_trailing_slash_required(self):
#         """Assert route without trailing slash fails to connect."""
#         connected = async_to_sync(_try_connect)('ws/synapse/test')
#         self.assertFalse(connected)
#
#     def test_malformed_routes_rejected(self):
#         """Assert malformed paths do not match."""
#         malformed = ['ws/synapse/', 'ws/synapse', 'ws/synapse///']
#         for route in malformed:
#             with self.subTest(route=route):
#                 connected = async_to_sync(_try_connect)(route)
#                 self.assertFalse(connected)
