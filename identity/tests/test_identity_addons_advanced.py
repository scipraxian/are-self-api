"""Tests for extended identity addons (memory snapshot, skills, platform, tool guidance)."""

from django.utils import timezone

from common.tests.common_test_case import CommonFixturesAPITestCase
from frontal_lobe.models import ReasoningSession, ReasoningStatusID, ReasoningTurn
from hippocampus.models import Engram, EngramTag, SkillEngram
from hypothalamus.models import AIModel, AIModelProvider, AIModelProviderUsageRecord, LLMProvider
from identity.addons.addon_registry import ADDON_REGISTRY
from identity.addons.memory_snapshot_addon import (
    AGENT_MEMORY_TAG,
    MAX_MEMORY_BLOCK_CHARS,
    USER_PROFILE_TAG,
    memory_snapshot_addon,
)
from identity.addons.platform_hint_addon import PLATFORM_HINTS, platform_hint_addon
from identity.addons.skills_index_addon import MAX_SKILLS_BLOCK_CHARS, SKILL_TAG, skills_index_addon
from identity.addons.tool_guidance_addon import (
    MAX_TOOL_GUIDANCE_CHARS,
    tool_guidance_addon,
)
from identity.models import IdentityDisc
from parietal_lobe.models import ToolDefinition
from talos_gateway.models import GatewaySession, GatewaySessionStatusID


class MemorySnapshotAddonTests(CommonFixturesAPITestCase):
    """Assert memory_snapshot_addon formats IdentityDisc.memories with tags."""

    def setUp(self):
        super().setUp()
        self.disc = IdentityDisc.objects.create(name='Layer3 Test Disc')

    def _tag(self, name):
        return EngramTag.objects.get_or_create(name=name)[0]

    def _engram(self, name, description, is_active=True, tags=None):
        e = Engram.objects.create(name=name, description=description, is_active=is_active)
        if tags:
            e.tags.set(tags)
        return e

    def test_returns_empty_when_no_qualifying_engrams(self):
        """Assert addon returns [] when memories M2M is empty."""
        session = ReasoningSession.objects.create(
            identity_disc=self.disc, total_xp=0
        )
        turn = ReasoningTurn.objects.create(
            session=session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )
        self.assertEqual(memory_snapshot_addon(turn), [])

    def test_excludes_inactive_and_untagged(self):
        """Assert is_active=False and engrams without profile/agent tags are omitted."""
        t_user = self._tag(USER_PROFILE_TAG)
        t_agent = self._tag(AGENT_MEMORY_TAG)
        bad = self._engram('x', 'hidden', is_active=False, tags=[t_user])
        orphan = self._engram('y', 'no tags', tags=[])
        good = self._engram('z', 'kept', tags=[t_user])
        self.disc.memories.add(bad, orphan, good)
        session = ReasoningSession.objects.create(
            identity_disc=self.disc, total_xp=0
        )
        turn = ReasoningTurn.objects.create(
            session=session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )
        out = memory_snapshot_addon(turn)
        self.assertEqual(len(out), 1)
        body = out[0]['content']
        self.assertIn('kept', body)
        self.assertNotIn('hidden', body)
        self.assertNotIn('no tags', body)

    def test_user_and_agent_sections_and_dual_tag(self):
        """Assert sections split by tag; dual-tagged engrams appear in both lists."""
        t_u = self._tag(USER_PROFILE_TAG)
        t_a = self._tag(AGENT_MEMORY_TAG)
        only_user = self._engram('u1', 'profile line', tags=[t_u])
        only_agent = self._engram('a1', 'agent line', tags=[t_a])
        both = self._engram('both', 'dual line', tags=[t_u, t_a])
        self.disc.memories.add(only_user, only_agent, both)
        session = ReasoningSession.objects.create(
            identity_disc=self.disc, total_xp=0
        )
        turn = ReasoningTurn.objects.create(
            session=session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )
        body = memory_snapshot_addon(turn)[0]['content']
        self.assertIn('### User Profile', body)
        self.assertIn('### Agent Notes', body)
        self.assertIn('- profile line', body)
        self.assertIn('- agent line', body)
        self.assertEqual(body.count('dual line'), 2)

    def test_orders_by_modified_desc(self):
        """Assert more recently modified engrams appear earlier within each section."""
        t_u = self._tag(USER_PROFILE_TAG)
        older = self._engram('old', 'first', tags=[t_u])
        newer = self._engram('new', 'second', tags=[t_u])
        self.disc.memories.add(older, newer)
        session = ReasoningSession.objects.create(
            identity_disc=self.disc, total_xp=0
        )
        turn = ReasoningTurn.objects.create(
            session=session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )
        body = memory_snapshot_addon(turn)[0]['content']
        pos_second = body.index('second')
        pos_first = body.index('first')
        self.assertLess(pos_second, pos_first)

    def test_truncates_total_block_to_cap_with_ellipsis(self):
        """Assert output length is capped at MAX_MEMORY_BLOCK_CHARS with ellipsis."""
        t_u = self._tag(USER_PROFILE_TAG)
        filler = 'Z' * 900
        a = self._engram('a', filler, tags=[t_u])
        b = self._engram('b', filler, tags=[t_u])
        self.disc.memories.add(a, b)
        session = ReasoningSession.objects.create(
            identity_disc=self.disc, total_xp=0
        )
        turn = ReasoningTurn.objects.create(
            session=session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )
        body = memory_snapshot_addon(turn)[0]['content']
        self.assertLessEqual(len(body), MAX_MEMORY_BLOCK_CHARS)
        self.assertTrue(body.endswith('...'))


class SkillsIndexAddonTests(CommonFixturesAPITestCase):
    """Assert skills_index_addon lists skill-tagged engrams that match enabled tools."""

    def setUp(self):
        super().setUp()
        self.disc = IdentityDisc.objects.create(name='Skills Test Disc')
        self.session = ReasoningSession.objects.create(
            identity_disc=self.disc, total_xp=0
        )

    def _skill_tag(self):
        return EngramTag.objects.get_or_create(name=SKILL_TAG)[0]

    def test_empty_when_no_skill_engrams_or_no_intersection(self):
        """Assert [] when no skill tag or tool name does not match enabled tools."""
        turn = ReasoningTurn.objects.create(
            session=self.session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )
        self.assertEqual(skills_index_addon(turn), [])

        tool = ToolDefinition.objects.create(
            name='mcp_layer3_alpha', description='Alpha tool'
        )
        self.disc.enabled_tools.add(tool)
        st = self._skill_tag()
        e = Engram.objects.create(
            name='wrong_name',
            description='x',
            is_active=True,
        )
        e.tags.add(st)
        e.identity_discs.add(self.disc)
        self.assertEqual(skills_index_addon(turn), [])

    def test_includes_matching_skill_rows_and_respects_case(self):
        """Assert engram.name matches enabled ToolDefinition case-insensitively."""
        tool = ToolDefinition.objects.create(
            name='MCP_Layer3_Beta', description='Beta does things'
        )
        self.disc.enabled_tools.add(tool)
        st = self._skill_tag()
        e = Engram.objects.create(
            name='mcp_layer3_beta',
            description='Skill body',
            is_active=True,
        )
        e.tags.add(st)
        e.identity_discs.add(self.disc)
        turn = ReasoningTurn.objects.create(
            session=self.session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )
        out = skills_index_addon(turn)
        self.assertEqual(len(out), 1)
        body = out[0]['content']
        self.assertIn('## Available Skills', body)
        self.assertIn('| mcp_layer3_beta |', body)
        self.assertIn('Skill body', body)

    def test_overflow_appends_and_n_more_notice(self):
        """Assert table drops trailing rows and appends ...and N more past char cap."""
        tools = []
        rows_data = []
        for i in range(12):
            t = ToolDefinition.objects.create(
                name=f'skill_tool_{i}', description='t'
            )
            tools.append(t)
            self.disc.enabled_tools.add(t)
            st = self._skill_tag()
            e = Engram.objects.create(
                name=f'skill_tool_{i}',
                description='D' * 400,
                is_active=True,
            )
            e.tags.add(st)
            e.identity_discs.add(self.disc)
            rows_data.append((f'skill_tool_{i}', e))
        turn = ReasoningTurn.objects.create(
            session=self.session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )
        body = skills_index_addon(turn)[0]['content']
        self.assertLessEqual(len(body), MAX_SKILLS_BLOCK_CHARS)
        self.assertIn('...and ', body)
        self.assertIn(' more', body)

    def test_skill_engram_appears_in_addon(self):
        """Assert SkillEngram linked to disc shows in addon output."""
        SkillEngram.objects.create(
            name='my_new_skill',
            description='A brand new skill from SkillEngram.',
            body='# Skill Body',
            identity_disc=self.disc,
        )
        turn = ReasoningTurn.objects.create(
            session=self.session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )
        out = skills_index_addon(turn)
        self.assertEqual(len(out), 1)
        body = out[0]['content']
        self.assertIn('my_new_skill', body)
        self.assertIn('A brand new skill from SkillEngram.', body)

    def test_skill_engram_no_tool_match_required(self):
        """Assert SkillEngram does not require tool name match (unlike Engram path)."""
        SkillEngram.objects.create(
            name='standalone_skill',
            description='No matching tool needed.',
            body='# Independent',
            identity_disc=self.disc,
        )
        turn = ReasoningTurn.objects.create(
            session=self.session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )
        out = skills_index_addon(turn)
        self.assertEqual(len(out), 1)
        self.assertIn('standalone_skill', out[0]['content'])

    def test_fallback_to_tagged_engrams_when_no_skill_engrams(self):
        """Assert tagged Engrams still work when no SkillEngram rows exist."""
        tool = ToolDefinition.objects.create(
            name='fallback_tool', description='Fallback desc'
        )
        self.disc.enabled_tools.add(tool)
        st = self._skill_tag()
        e = Engram.objects.create(
            name='fallback_tool',
            description='Old-style skill.',
            is_active=True,
        )
        e.tags.add(st)
        e.identity_discs.add(self.disc)
        turn = ReasoningTurn.objects.create(
            session=self.session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )
        out = skills_index_addon(turn)
        self.assertEqual(len(out), 1)
        self.assertIn('fallback_tool', out[0]['content'])


class PlatformHintAddonTests(CommonFixturesAPITestCase):
    """Assert platform_hint_addon reads GatewaySession.platform."""

    fixtures = list(CommonFixturesAPITestCase.fixtures) + [
        'talos_gateway/fixtures/initial_data.json',
    ]

    def test_discord_platform_returns_hint_block(self):
        """Assert discord maps to PLATFORM_HINTS content."""
        disc = IdentityDisc.objects.create(name='GW Disc')
        session = ReasoningSession.objects.create(identity_disc=disc, total_xp=0)
        GatewaySession.objects.create(
            platform='discord',
            channel_id='c1',
            reasoning_session=session,
            status_id=GatewaySessionStatusID.ACTIVE,
            last_activity=timezone.now(),
        )
        turn = ReasoningTurn.objects.create(
            session=session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )
        out = platform_hint_addon(turn)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['content'], PLATFORM_HINTS['discord'])

    def test_unknown_platform_returns_empty(self):
        """Assert unrecognized platform yields []."""
        disc = IdentityDisc.objects.create(name='GW Disc 2')
        session = ReasoningSession.objects.create(identity_disc=disc, total_xp=0)
        GatewaySession.objects.create(
            platform='unknown_os',
            channel_id='c2',
            reasoning_session=session,
            status_id=GatewaySessionStatusID.ACTIVE,
            last_activity=timezone.now(),
        )
        turn = ReasoningTurn.objects.create(
            session=session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )
        self.assertEqual(platform_hint_addon(turn), [])

    def test_no_gateway_session_returns_empty(self):
        """Assert no GatewaySession row yields []."""
        disc = IdentityDisc.objects.create(name='GW Disc 3')
        session = ReasoningSession.objects.create(identity_disc=disc, total_xp=0)
        turn = ReasoningTurn.objects.create(
            session=session,
            turn_number=1,
            status_id=ReasoningStatusID.ACTIVE,
        )
        self.assertEqual(platform_hint_addon(turn), [])


class ToolGuidanceAddonTests(CommonFixturesAPITestCase):
    """Assert tool_guidance_addon keys off last turn weak model and enabled tools."""

    def setUp(self):
        super().setUp()
        self.model = AIModel.objects.create(
            name='tg-model', context_length=131072
        )
        self.provider = LLMProvider.objects.create(
            key='tg-prov', base_url='http://test.com'
        )

    def _make_usage(self, provider_unique_model_id):
        amp = AIModelProvider.objects.filter(
            provider_unique_model_id=provider_unique_model_id
        ).first()
        if not amp:
            amp = AIModelProvider.objects.create(
                ai_model=self.model,
                provider=self.provider,
                provider_unique_model_id=provider_unique_model_id,
            )
        return AIModelProviderUsageRecord.objects.create(
            ai_model_provider=amp,
            ai_model=self.model,
            request_payload=[],
            response_payload={},
        )

    def _turn_chain(self, provider_id_weak: str, add_tools: bool):
        disc = IdentityDisc.objects.create(name='TG Disc')
        if add_tools:
            td = ToolDefinition.objects.create(
                name='mcp_terminal', description='Runs shell commands.'
            )
            disc.enabled_tools.add(td)
        session = ReasoningSession.objects.create(identity_disc=disc, total_xp=0)
        usage1 = self._make_usage(provider_id_weak)
        t1 = ReasoningTurn.objects.create(
            session=session,
            turn_number=1,
            model_usage_record=usage1,
            status_id=ReasoningStatusID.COMPLETED,
        )
        # Second ledger must use a distinct provider_unique_model_id (unique field).
        usage2 = self._make_usage('other/placeholder-model')
        turn2 = ReasoningTurn.objects.create(
            session=session,
            turn_number=2,
            last_turn=t1,
            model_usage_record=usage2,
            status_id=ReasoningStatusID.ACTIVE,
        )
        return turn2

    def test_turn_one_has_no_last_turn_returns_empty(self):
        """Assert first turn cannot classify prior model and returns []."""
        disc = IdentityDisc.objects.create(name='TG T1')
        td = ToolDefinition.objects.create(name='t', description='d')
        disc.enabled_tools.add(td)
        session = ReasoningSession.objects.create(identity_disc=disc, total_xp=0)
        usage = self._make_usage('openai/gpt-4o-mini')
        turn = ReasoningTurn.objects.create(
            session=session,
            turn_number=1,
            model_usage_record=usage,
            last_turn=None,
            status_id=ReasoningStatusID.ACTIVE,
        )
        self.assertEqual(tool_guidance_addon(turn), [])

    def test_weak_model_with_tools_returns_guidance(self):
        """Assert substring match on provider id and non-empty enabled tools."""
        turn2 = self._turn_chain('openai/gpt-4o-mini', add_tools=True)
        out = tool_guidance_addon(turn2)
        self.assertEqual(len(out), 1)
        body = out[0]['content']
        self.assertIn('## Available Tools', body)
        self.assertIn('mcp_terminal', body)

    def test_strong_model_returns_empty(self):
        """Assert Claude Opus id does not match weak-tool needles."""
        disc = IdentityDisc.objects.create(name='Strong')
        td = ToolDefinition.objects.create(name='tool_a', description='d')
        disc.enabled_tools.add(td)
        session = ReasoningSession.objects.create(identity_disc=disc, total_xp=0)
        usage1 = self._make_usage('anthropic/claude-opus-4')
        t1 = ReasoningTurn.objects.create(
            session=session,
            turn_number=1,
            model_usage_record=usage1,
            status_id=ReasoningStatusID.COMPLETED,
        )
        usage2 = self._make_usage('x/x')
        turn2 = ReasoningTurn.objects.create(
            session=session,
            turn_number=2,
            last_turn=t1,
            model_usage_record=usage2,
            status_id=ReasoningStatusID.ACTIVE,
        )
        self.assertEqual(tool_guidance_addon(turn2), [])

    def test_weak_model_without_tools_returns_empty(self):
        """Assert weak model alone yields [] when enabled_tools is empty."""
        turn2 = self._turn_chain('openai/gpt-4-turbo', add_tools=False)
        self.assertEqual(tool_guidance_addon(turn2), [])

    def test_respects_character_cap(self):
        """Assert guidance body is at most MAX_TOOL_GUIDANCE_CHARS."""
        disc = IdentityDisc.objects.create(name='Many Tools')
        for i in range(30):
            td = ToolDefinition.objects.create(
                name=f'tool_{i}', description='Long description ' * 20
            )
            disc.enabled_tools.add(td)
        session = ReasoningSession.objects.create(identity_disc=disc, total_xp=0)
        usage1 = self._make_usage('gpt-4')
        t1 = ReasoningTurn.objects.create(
            session=session,
            turn_number=1,
            model_usage_record=usage1,
            status_id=ReasoningStatusID.COMPLETED,
        )
        usage2 = self._make_usage('y')
        turn2 = ReasoningTurn.objects.create(
            session=session,
            turn_number=2,
            last_turn=t1,
            model_usage_record=usage2,
            status_id=ReasoningStatusID.ACTIVE,
        )
        body = tool_guidance_addon(turn2)[0]['content']
        self.assertLessEqual(len(body), MAX_TOOL_GUIDANCE_CHARS)


class ExtendedAddonRegistryTests(CommonFixturesAPITestCase):
    """Assert extended-addon fixture slugs resolve in ADDON_REGISTRY."""

    fixtures = list(CommonFixturesAPITestCase.fixtures) + [
        'identity/fixtures/layer3_addons.json',
    ]

    def test_extended_addon_slugs_registered(self):
        """Assert all four function_slug values from fixtures are callable."""
        for slug in (
            'memory_snapshot_addon',
            'skills_index_addon',
            'platform_hint_addon',
            'tool_guidance_addon',
        ):
            self.assertIn(slug, ADDON_REGISTRY)
            self.assertTrue(callable(ADDON_REGISTRY[slug]))
