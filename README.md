<p align="center">
  <a href="https://are-self.com">
    <img src="https://are-self.com/img/ui/cns-graph-hero.png" alt="The Are-Self CNS pathway editor — Begin, List Location, Frontal Lobe, Gate, Retry, and Delay nodes wired together with success and fail edges on a dotted dark canvas." width="900">
  </a>
</p>

# Are-Self

### Made for big tech, brave teachers, and poor kids.

**Free. Local. Private. MIT licensed. On hardware you already own.**

`Open · Local · MIT · Built solo since January 2026 · ~57K Python · ~15K tests · 0 cloud calls required`

An open-source, neurologically-inspired AI reasoning swarm — bringing free AI to underserved youth, curious adults, and anyone else the subscription economy forgot.

[**Read the site →**](https://are-self.com)  ·  [**See it run end-to-end →**](https://are-self.com/docs/end-to-end)  ·  [**Install →**](https://are-self.com/docs/quick-start)  ·  [**Come along →**](https://are-self.com/docs/state#how-to-come-along)

## State of the work

```
Core platform                ▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▱  ~95% to 1.0
NeuralModifiers & curriculum ▰▰▰▰▰▰▰▰▰▰▰▱▱▱▱▱▱▱▱▱  ~55% (growing forever)
```

Started January 2, 2026. Released MIT-licensed and public April 7, 2026. Honest progress page: [are-self.com/docs/state](https://are-self.com/docs/state).

---

## What it is

Are-Self lets small, free, local language models work together as a swarm — reasoning autonomously, using tools, forming memories, and managing their own work. It runs on consumer hardware via Ollama, with cloud models as optional failover.

The architecture is modeled after the human brain. Each component maps to a real brain region and does what that region actually does: the Hippocampus holds memory, the Frontal Lobe reasons, the Hypothalamus keeps the bill down, the Central Nervous System executes pathways tick by tick. The architecture is the documentation.

## What's different about it

If you've used [Ollama](https://ollama.com), Are-Self runs on top of it — the models you've already pulled are the ones Are-Self thinks with.

If you've reached for an agent framework like [autogen](https://github.com/microsoft/autogen), [crewAI](https://github.com/joaomdmoura/crewAI), or [LangGraph](https://github.com/langchain-ai/langgraph), Are-Self is in the same neighborhood with one structural difference: every coordination role is named for the part of the brain that does it. You're inside neuroanatomy instead of debugging a `coordinator` or a `manager`. The system compensates for small models' limitations — short context, weak instruction following — with mechanical structure rather than raw capability. A 7B model does real work when the architecture handles the hard parts.

If you've reached for a hosted agent runtime, Are-Self is the local-first answer. Zero cloud calls required. Unplug the ethernet cable, the AIs keep working.

## See it run

[![Are-Self — The Grid Is Free](https://img.youtube.com/vi/UUX-T2aTZlI/maxresdefault.jpg)](https://youtu.be/UUX-T2aTZlI)

The end-to-end walkthrough at [are-self.com/docs/end-to-end](https://are-self.com/docs/end-to-end) is sixteen screenshots from a single clean run on 2026-04-21 — Identity forged, Pathway built, SpikeTrain fired, Frontal Lobe reasoning captured, tools logged, Nerve Terminal reporting. The whole tick cycle in one page.

## The brain

Every part of Are-Self maps to a brain region. This is how you navigate the system.

| Region | Route | What It Does |
|---|---|---|
| **Identity** | `/identity` | Create AI personas with tools, personality, and budget |
| **Temporal Lobe** | `/temporal` | Set up work cycles with shifts and participants |
| **Prefrontal Cortex** | `/pfc` | Assign and manage tasks (epics, stories, tasks) |
| **Hypothalamus** | `/hypothalamus` | Model catalog, pricing, selection, circuit breakers |
| **Central Nervous System** | `/cns` | Execution engine — pathways, spike trains, neurons |
| **Frontal Lobe** | `/frontal` | Reasoning sessions — watch the AIs think in real time |
| **Hippocampus** | `/hippocampus` | Memory — vector-embedded facts that persist across sessions |
| **Parietal Lobe** | — | Tool execution gateway (no UI, runs server-side) |
| **Peripheral Nervous System** | `/pns` | Worker fleet monitoring |
| **Thalamus** | floating bubble | Chat interface — talk to the system from any page |

## The lifecycle

1. **Create an Identity** — a persona with a system prompt, tools, and model preferences
2. **Configure models** — the Hypothalamus manages which LLMs are available and how much they cost
3. **Build an Iteration** — a work cycle with shifts (planning, executing, reviewing) and turn limits
4. **Forge Identities into Discs** — deploy personas into the iteration as working instances
5. **Assign tasks** — the Prefrontal Cortex manages the backlog
6. **Let it tick** — the PNS heartbeat triggers the cycle: temporal lobe wakes → CNS fires → frontal lobe reasons → tools execute → memories form
7. **Watch and interact** — monitor spike trains, read reasoning logs, inject messages into active sessions

## Install

You'll need Python 3.12+, Docker Desktop, Node.js 20+, and Ollama. Then:

```bash
git clone https://github.com/scipraxian/are-self-api
git clone https://github.com/scipraxian/are-self-ui
cd are-self-api
are-self-install.bat   # Windows; macOS/Linux: see the guide
```

The full guide — with prerequisite installers, the macOS/Linux step list, a troubleshooting section, and the *"your new install buddy"* tip on using a local llama3.2 to walk you through any step you get stuck on — lives at **[are-self.com/docs/quick-start](https://are-self.com/docs/quick-start)**.

## How to come along

Are-Self is solo for now. Everyone is welcome. The mission is free local AI in the hands of the kid who otherwise wouldn't get any — and there are real doors into that mission, only one of which goes through me.

Many ways in:

1. **Put a machine in a kid's hands.** A used 16GB laptop runs the whole stack. If you can gift one to a kid in your family, your neighborhood, your school, your congregation — that's the mission, and it doesn't go through me at all.
2. **Get a community org to deploy it.** Library, school, church, after-school program, 501(c)(3). If you can broker an intro to a group that wants free AI in front of kids who don't have it, that's the kind of unlock the project is built for.
3. **Write a course.** Eleven of twelve drafted courses still need the v1.5 rubric pattern rolled out. Repo: [are-self-learn](https://github.com/scipraxian/are-self-learn).
4. **Write a paper.** Flagship has open Evaluation sections; five more are seeded outlines. Repo: [are-self-research](https://github.com/scipraxian/are-self-research).
5. **Write code, or write the working method.** Pick a `TASKS.md` item or ship a NeuralModifier for the thing you wish existed. PRs against `CLAUDE.md` and the operating-notes files count too — see the next section.
6. **If you'd like this project to keep going at the pace it's been going, supporting the human typing it forward is one direct lever.** Roughly $5–7 a day in AI tooling, out-of-pocket on Anthropic's Claude Max plan. Since January 2, 2026 that has bought ~57K lines of Python, ~15K matching test lines, eleven brain regions wired and shipping, the Modifier Garden installable-modifier system, an MCP server with 14 tools, fifteen courses in [are-self-learn](https://github.com/scipraxian/are-self-learn), six research papers seeded, the [Mira storybook](https://are-self.com/docs/storybook), the docs site, and a daily *Walk with Frith* dev log.
   - [GitHub Sponsors](https://github.com/sponsors/scipraxian)
   - [Ko-fi](https://ko-fi.com/scipraxian)
   - [Buy Me a Coffee](https://buymeacoffee.com/scipraxian)
   - [Patreon](https://patreon.com/scipraxian)

The work happens either way. Where you come in shapes how fast it moves and how many kids it reaches.

The full state — what works, what's broken, what's planned — is at [are-self.com/docs/state](https://are-self.com/docs/state). It's honest. It's a status.

## Stack

- **Backend:** Django 6.x, Daphne (ASGI), Celery 5.x, Redis, PostgreSQL + pgvector
- **Frontend:** React, Vite, TypeScript ([are-self-ui](https://github.com/scipraxian/are-self-ui))
- **LLM Providers:** Ollama (local), OpenRouter (cloud failover), via LiteLLM
- **Embeddings:** nomic-embed-text (768-dim, runs locally via Ollama)
- **Real-time:** Django Channels (WebSocket) with typed neurotransmitter events

## Built With

Are-Self stands on the shoulders of these projects and communities:

| Project | Role in Are-Self |
|---|---|
| [Ollama](https://ollama.com) | Local model inference — the engine that makes "AI on your hardware" real |
| [LiteLLM](https://github.com/BerriAI/litellm) | Universal LLM routing — one interface for every model provider |
| [OpenRouter](https://openrouter.ai) | Cloud failover when local isn't enough |
| [Gemma](https://ai.google.dev/gemma) | Tool-calling workhorse from Google DeepMind |
| [Llama](https://llama.meta.com) | The model family that opened the floodgates |
| [Mistral](https://mistral.ai) | Efficient models that punch above their weight |
| [Qwen](https://github.com/QwenLM/Qwen) | Multilingual reasoning and strong tool use |
| [nomic-embed-text](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5) | 768-dim embeddings powering the Hippocampus memory system |
| [Django](https://www.djangoproject.com) | Backend framework — the skeleton of the brain |
| [React](https://react.dev) | Frontend UI ([are-self-ui](https://github.com/scipraxian/are-self-ui)) |
| [Celery](https://docs.celeryq.dev) + [Redis](https://redis.io) | Task orchestration and message brokering |
| [PostgreSQL](https://www.postgresql.org) + [pgvector](https://github.com/pgvector/pgvector) | Relational storage + vector similarity search |

Full acknowledgments: [are-self.com/docs/acknowledgments](https://are-self.com/docs/acknowledgments)

## Working with AI, in the open

Every repo here carries a `CLAUDE.md` and a small set of operating-notes files at its root — the actual prompts, conventions, and session protocols this project uses to cooperate with AI day to day. They're committed, public, and forkable. Pull requests against those files are as welcome as pull requests against the code; the cooperation pattern is one of the things this project wants to be good at, and the audience for that pattern is anyone who reads it.

Five AI collaborators contributed during implementation. Claude was by far the best of them. The architecture is human. The typing had help. The decision to give it away is human. The choice to keep doing it openly, with the prompts checked in next to the code, is the part that's up for sharing.

## More

Local repo docs: [ARCHITECTURE.md](ARCHITECTURE.md) · [GETTING_STARTED.md](GETTING_STARTED.md) · [FEATURES.md](FEATURES.md) · [API_REFERENCE.md](API_REFERENCE.md) · [SECURITY.md](SECURITY.md) · [DEPENDENCY_AUDIT.md](DEPENDENCY_AUDIT.md) · [CONTRIBUTING.md](CONTRIBUTING.md)

The fuller documentation — guides, FAQ, UI walkthroughs, brain-region deep dives, the philosophy underneath — is at [are-self.com](https://are-self.com).

## Find us

[YouTube](https://youtube.com/@scipraxian) · [Discord](https://discord.gg/nGFFcxxV) · [Facebook](https://facebook.com/scipraxian) · [X](https://x.com/scipraxian) · [Truth Social](https://truthsocial.com/@scipraxian) · [TikTok](https://tiktok.com/@scipraxian) · [Instagram](https://instagram.com/scipraxian/) · [Reddit](https://reddit.com/user/Scipraxian/)

## License

MIT. The Grid is free.

---

If any of this caught you, the real welcome is at **[are-self.com](https://are-self.com)**. Star this if you want a kid with a laptop to be able to run a real AI swarm without paying a corporation a dime.
