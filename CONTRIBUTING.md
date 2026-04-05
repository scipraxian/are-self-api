# Contributing to Are-Self

Welcome. We're building AI infrastructure for the people — especially those who've been left out of the AI revolution. If you believe AI should be a public good and want to help make that real, you're in the right place.

This is an MIT-licensed, neuro-mimetic AI orchestration framework. Every contribution matters, whether you're writing code, documenting features, improving accessibility, or just helping someone else get started.

## Our Mission

Are-Self is designed to make AI accessible to underserved communities. We're building toward a 501(c)(3) nonprofit. Whether you're an educator, student, researcher, or just someone who cares about equitable AI — we want your help.

## Getting Started

### Setting Up Your Development Environment

**Prerequisites:**
- Python 3.11+
- PostgreSQL 14+
- Redis 6+
- Node.js 18+ (for frontend work)
- Docker (optional, recommended)

**Quick Setup:**

On Windows, run the included installation script:
```bash
are-self-install.bat
```

For manual setup or other platforms:

1. Clone the repository:
```bash
git clone https://github.com/scipraxian/are-self.git
cd are-self/are-self-api
```

2. Create a Python virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt  # For development tools
```

4. Set up the database:
```bash
python manage.py migrate
python manage.py createsuperuser  # Create an admin user for testing
```

5. Start Redis (required for Celery):
```bash
redis-server
```

6. Start the development server:
```bash
daphne -b 0.0.0.0 -p 8000 are_self.asgi:application
```

7. In another terminal, start the Celery worker:
```bash
celery -A are_self worker -l info
```

The API will be available at `http://localhost:8000`.

### Frontend Development

The Are-Self UI lives in a separate repository. For fullstack development:

```bash
git clone https://github.com/scipraxian/are-self-ui.git
cd are-self-ui
npm install
npm run dev
```

See the are-self-ui repository for its specific setup instructions.

## Code Style Guide

We maintain consistency across the codebase to make it easier for everyone to contribute and review code.

**For complete style guidelines, see [STYLE_GUIDE.md](./STYLE_GUIDE.md)**

Quick reference:
- **Functions:** `snake_case`
- **Classes:** `PascalCase`
- **Logging:** Use `%s` formatting (not f-strings for logging)
- **Line length:** 88 characters maximum
- **Strings:** Single quotes preferred
- **Nested functions:** Avoid them — keep functions at module level for testability

Example:
```python
class NeuronOrchestratorManager:
    """Manages orchestration across neuro-mimetic agents."""

    def coordinate_signal_flow(self, region_id, signal_payload):
        """Route signals between brain regions."""
        logger.info('Routing signal %s to region %s', signal_payload['id'], region_id)
        # Implementation here
```

## Testing

We believe in real tests with real databases.

- Use `CommonFixturesAPITestCase` as your base test class
- Tests run against a real PostgreSQL instance (test database)
- Use `async_to_sync` when testing async code
- Each test should be independent and clean up after itself
- Aim for tests that verify behavior, not implementation details

Example test structure:
```python
from tests.fixtures import CommonFixturesAPITestCase

class HippocampusMemoryTestCase(CommonFixturesAPITestCase):
    """Tests for the Hippocampus (memory) brain region."""

    def test_memory_encoding_and_retrieval(self):
        """Verify memories are encoded and retrievable."""
        memory = self.create_test_memory(content='test')
        retrieved = Memory.objects.get(id=memory.id)
        self.assertEqual(retrieved.content, 'test')
```

Run tests:
```bash
python manage.py test
```

## Submitting a Pull Request

1. **Fork the repository** and create a feature branch:
```bash
git checkout -b feature/my-contribution
```

2. **Make your changes** following the code style guide above.

3. **Write or update tests** for your changes. All new code should have tests.

4. **Update documentation** if you've changed functionality or added new features.

5. **Run tests locally** to ensure everything passes:
```bash
python manage.py test
```

6. **Push to your fork** and open a pull request against the main repository.

In your PR description, please:
- Describe what problem you're solving or feature you're adding
- Explain *why* this change matters
- Note any new dependencies or environment setup needed
- Reference any related issues with `Closes #123`

Example PR template:
```
## What does this do?
Adds pgvector integration to the Cortex brain region for semantic memory storage.

## Why?
This enables the system to understand semantic relationships between concepts,
improving reasoning across connected neural pathways.

## Testing
Added 8 tests covering vector encoding, similarity search, and edge cases.
All existing tests pass.
```

## Reporting Issues

Found a bug? Want to suggest a feature? We'd love to hear about it.

**When reporting an issue:**
- Use a clear, descriptive title
- Describe the current behavior and what you expected to happen
- Include steps to reproduce (if it's a bug)
- Share your environment details (OS, Python version, etc.)
- Include relevant error messages or logs
- Attach screenshots if it's UI-related

**Label your issue:**
- `bug` — Something isn't working as expected
- `feature` — New functionality you'd like to see
- `documentation` — Improvements to docs or guides
- `good first issue` — Great for newcomers
- `help wanted` — We're actively looking for contributions here

## Architecture Overview

Are-Self is built around a neuro-mimetic architecture where **every Django app is a brain region**. This isn't metaphorical — the structure maps to actual brain functions:

- **Hippocampus** — Memory and experience storage
- **Cortex** — Reasoning and semantic understanding
- **Amygdala** — Emotional context and response
- **Cerebellum** — Motor coordination and actions
- And more...

For a deep dive into the architecture, philosophy, and design decisions, see [ARCHITECTURE.md](./ARCHITECTURE.md).

## Tech Stack

- **Backend:** Django 6.x with Daphne ASGI
- **Task Queue:** Celery 5.x with Redis
- **Database:** PostgreSQL with pgvector extension
- **Frontend:** React + Vite + TypeScript (separate repo)
- **LLM Integration:** LiteLLM with support for:
  - Ollama (local deployment)
  - OpenRouter (cloud failover)

## Where We Need Help

We're actively seeking contributions in these areas:

### Testing
- Expanding test coverage for existing brain regions
- Adding integration tests for multi-region workflows
- Performance and stress testing

### Documentation
- Tutorial content for common workflows
- Architecture deep-dives for specific brain regions
- API endpoint documentation
- Deployment guides for different environments

### Tool Development
- Brain region implementations
- LLM provider integrations
- Data import/export tools
- Monitoring and observability tools

### Accessibility
- Ensuring the UI is fully accessible (WCAG 2.1 AA)
- Documentation in multiple formats
- Testing with assistive technologies

### Community
- Help onboarding new contributors
- Answer questions in issues and discussions
- Share your projects built with Are-Self

## Code of Conduct

We're building for everyone, and we mean it.

**Be kind.** Assume good intent. We're all learning.

**Be respectful.** Disagree thoughtfully. Different perspectives make us better.

**Be inclusive.** Welcome people from all backgrounds and experience levels. Especially those left out of tech.

**No harassment.** This includes discrimination based on race, ethnicity, gender, sexual orientation, disability, religion, or anything else. We don't tolerate it.

**Lead by example.** The tone we set in code reviews, discussions, and conversations matters.

If you see something that doesn't fit these values, reach out to Michael (scipraxian) directly. We'll address it.

## Questions?

- Check existing issues and discussions
- Open a new discussion if you can't find an answer
- Reach out to Michael at scipraxian on GitHub
- Read through [ARCHITECTURE.md](./ARCHITECTURE.md) and [STYLE_GUIDE.md](./STYLE_GUIDE.md)

---

**Thank you for being part of this.** Whether this is your first open-source contribution or your hundredth, we're glad you're here. Every line of code, every test, every piece of documentation brings us closer to AI that serves everyone.

Let's build something that matters.
