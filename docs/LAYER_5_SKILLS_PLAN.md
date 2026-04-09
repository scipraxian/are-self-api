# Layer 5: Skills as Knowledge

**Path B — Layer 5 Implementation Plan**  
**Date:** 2026-04-07  
**Estimated Scope:** Model + CRUD + migration, ~800-1,200 lines, 1 week  
**Prerequisites:** Layer 1 (mcp_memory), Layer 3 (skills_index_addon), working Hippocampus.

---

## 1. The Design Decision

The Path B doc presents two options:

**Option A: SkillEngram model** — New dedicated model with name, description, body (markdown), yaml_frontmatter (JSON), plus FileAttachment records. Vector-embedded. Type-safe.

**Option B: Tagged Engrams with convention** — Use regular Engrams tagged "skill", store SKILL.md in description, metadata in a JSON field. No new model, less type-safe.

**Recommendation: Option A — SkillEngram model.**

Why: Skills are fundamentally different from memory entries. They have:
- Structured YAML frontmatter (name, description, category, trigger patterns)
- A markdown body with multi-section instructions
- Supporting files (scripts/, templates/, references/) that need to be tracked
- Create/patch/edit/delete/write_file/remove_file operations that mirror file system semantics
- An index format used in system prompt injection that memory doesn't need
- A size and complexity that justifies a dedicated model

Option B would work for a few skills, but breaks down at scale — you'd be stuffing SKILL.md content, YAML metadata, and file paths into a few overloaded Engram fields. The type safety and query clarity of a dedicated model are worth the migration cost.

---

## 2. SkillEngram Model

**File:** `hippocampus/models.py` (extend existing)

```python
class SkillEngram(CreatedMixin, ModifiedMixin):
    """Procedural knowledge unit: SKILL.md content + metadata + linked files."""
    
    name = models.CharField(max_length=64, db_index=True, unique=True)
    description = models.CharField(max_length=200)  # Compact for index display
    category = models.CharField(max_length=64, db_index=True, blank=True)
    body = models.TextField()  # Full SKILL.md markdown body
    yaml_frontmatter = models.JSONField(default=dict)  # trigger, author, etc.
    vector = VectorField(dimensions=768, null=True)  # Semantic embedding
    
    is_active = models.BooleanField(default=True)
    
    # Link to IdentityDisc (optional — skills can be global or persona-specific)
    identity_disc = models.ForeignKey(
        'identity.IdentityDisc',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='skill_engrams',
    )
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name
```

**FileAttachment Model** (for scripts/templates/references):

```python
class SkillFileAttachment(CreatedMixin):
    """A file belonging to a SkillEngram (script, template, reference)."""
    
    FILE_TYPES = [
        ('script', 'Script'),
        ('template', 'Template'),
        ('reference', 'Reference'),
        ('asset', 'Asset'),
    ]
    
    skill = models.ForeignKey(
        SkillEngram,
        on_delete=models.CASCADE,
        related_name='attached_files',
    )
    file_type = models.CharField(max_length=16, choices=FILE_TYPES)
    file_path = models.CharField(max_length=512)  # Relative path within skill directory
    file_content = models.TextField(blank=True)  # Full content of the file
    
    class Meta:
        unique_together = [['skill', 'file_path']]
        ordering = ['file_type', 'file_path']
    
    def __str__(self):
        return f'{self.file_type}: {self.file_path}'
```

**Migration:** `manage.py makemigrations hippocampus` → creates SkillEngram and SkillFileAttachment.

**Why this goes in hippocampus:** Skills are knowledge. The Hippocampus app already owns Engrams and vector embeddings. Keeping SkillEngram alongside Engram means a single `pip install` and `migrate` enables both. It also allows future hybridization (skills that reference engrams, engrams that are skill-generated).

---

## 3. Skill CRUD Operations

### 3.1 mcp_skill_manage Tool

**File:** `parietal_lobe/parietal_mcp/mcp_skill_manage.py` (~300 lines)

```python
def mcp_skill_manage(
    action: str,
    name: str = '',
    content: str = '',
    old_text: str = '',
    new_text: str = '',
    replace_all: bool = False,
    file_path: str = '',
    file_content: str = '',
    category: str = '',
) -> dict:
```

**Actions:**

| Action | Inputs | Behavior |
|--------|--------|----------|
| `create` | name, content, category | Parse YAML frontmatter from content, create SkillEngram + FileAttachments |
| `patch` | name, old_text, new_text, replace_all, file_path | Edit SKILL.md body or attached file content |
| `edit` | name, content | Full body rewrite (major overhaul) |
| `delete` | name | Set is_active=False (soft delete) |
| `write_file` | name, file_path, file_content | Create or update an attached file |
| `remove_file` | name, file_path | Delete an attached file from the skill |

**Create implementation:**
```python
import yaml

def _create_skill(name, content, category=''):
    # Parse YAML frontmatter
    yaml_data = {}
    body = content
    if content.startswith('---\n'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                yaml_data = yaml.safe_load(parts[1])
                body = parts[2].strip()
            except yaml.YAMLError:
                # If YAML parsing fails, treat entire content as body
                body = content
    
    # Validate
    if not name or len(name) > 64:
        return {"error": "Name must be 1-64 characters"}
    if SkillEngram.objects.filter(name=name, is_active=True).exists():
        return {"error": f"Skill '{name}' already exists"}
    
    # Create
    skill = SkillEngram.objects.create(
        name=name,
        description=yaml_data.get('description', '')[:200] or body[:200].split('\n')[0],
        category=category or yaml_data.get('category', ''),
        body=body,
        yaml_frontmatter=yaml_data,
        vector=None,  # Will be generated by post-save signal or on-demand
    )
    
    # Generate vector embedding
    _embed_skill(skill)
    
    return {"status": "created", "name": name, "description": skill.description}
```

**Size limits:**
- name: max 64 chars (matches model CharField)
- description (from YAML): max 200 chars
- body: no hard limit (TextField), but practical limit ~50KB per skill
- file_content per attachment: no hard limit, but practical limit ~20KB

**ToolDefinition:**
- name: `mcp_skill_manage`
- category: `skills`
- description: `Manage skills: create, patch, edit, delete, write_file, remove_file. Skills are procedural knowledge units with YAML frontmatter and markdown body.`
- parameters: `action` (string, enum), `name` (string), `content` (string), `old_text` (string), `new_text` (string), `replace_all` (boolean), `file_path` (string), `file_content` (string), `category` (string)

---

### 3.2 mcp_skill_view Tool

**File:** `parietal_lobe/parietal_mcp/mcp_skill_view.py` (~60 lines)

```python
def mcp_skill_view(name: str, file_path: str = '') -> dict:
    """Load a skill's SKILL.md content and list attached files."""
    try:
        skill = SkillEngram.objects.get(name=name, is_active=True)
    except SkillEngram.DoesNotExist:
        return {"error": f"Skill '{name}' not found."}
    
    result = {
        "name": skill.name,
        "description": skill.description,
        "category": skill.category,
        "body": skill.body,
        "attached_files": [
            {
                "file_type": f.file_type,
                "file_path": f.file_path,
            }
            for f in skill.attached_files.all()
        ],
    }
    
    # If file_path specified, return that file's content
    if file_path:
        try:
            attachment = skill.attached_files.get(file_path=file_path)
            result["file_content"] = attachment.file_content
        except SkillFileAttachment.DoesNotExist:
            result["file_error"] = f"File '{file_path}' not found."
    
    return result
```

**ToolDefinition:**
- name: `mcp_skill_view`
- category: `skills`
- description: `View a skill's SKILL.md content and attached files.`
- parameters: `name` (string, required), `file_path` (string, optional)

---

### 3.3 mcp_skills_list Tool

**File:** `parietal_lobe/parietal_mcp/mcp_skills_list.py` (~30 lines)

```python
def mcp_skills_list(category: str = '') -> dict:
    """List available skills with name and description."""
    qs = SkillEngram.objects.filter(is_active=True)
    if category:
        qs = qs.filter(category=category)
    
    skills = [
        {"name": s.name, "description": s.description, "category": s.category}
        for s in qs.order_by('category', 'name')
    ]
    
    return {"skills": skills, "count": len(skills)}
```

**ToolDefinition:**
- name: `mcp_skills_list`
- category: `skills`
- description: `List available skills. Optionally filter by category.`
- parameters: `category` (string, optional)

**Note:** This is the tool used by the `skills_index_addon` (Layer 3) to build the compact skill catalog. It returns the same format the addon expects for system prompt injection.

---

## 4. Vector Embedding for Skills

Skills get embedded into 768-dimensional vectors for semantic retrieval. Reuse the Hippocampus embedding pipeline:

```python
def _embed_skill(skill: SkillEngram) -> None:
    """Generate and save vector embedding for a skill."""
    # Index text: name + description + first 2000 chars of body
    index_text = f"{skill.name}\n{skill.description}\n{skill.body[:2000]}"
    
    embeddings_client = get_embeddings_client()  # Reuse Hippocampus OllamaClient
    vector = embeddings_client.embed(index_text)
    
    skill.vector = vector
    skill.save(update_fields=['vector', 'modified'])
```

**Semantic skill lookup:** When FrontalLobe needs to determine which skills are relevant to a task, it can query by vector similarity:
```python
def find_skills_by_semantic(query: str, threshold: float = 0.75, limit: int = 5):
    query_vector = get_embeddings_client().embed(query)
    return SkillEngram.objects.filter(
        is_active=True, 
        vector__isnull=False
    ).annotate(
        distance=cosine_distance('vector', query_vector)
    ).filter(distance__lte=threshold).order_by('distance')[:limit]
```

---

## 5. Migration Script: Hermes Skills → Talos SkillEngram

**File:** `scripts/migrate_hermes_skills.py` (~200 lines)

Walks `~/.hermes/skills/` directory, one-time migration:

```python
import os
from pathlib import Path
import yaml

HERMES_SKILLS_DIR = Path.home() / '.hermes' / 'skills'

def migrate_all_skills():
    stats = {"created": 0, "skipped": 0, "errors": []}
    
    for skill_dir in sorted(HERMES_SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name.startswith('.'):
            continue
        
        stats = migrate_single_skill(skill_dir, stats)
    
    return stats

def migrate_single_skill(skill_dir: Path, stats: dict) -> dict:
    skill_md = skill_dir / 'SKILL.md'
    if not skill_md.exists():
        stats['errors'].append(f"{skill_dir.name}: no SKILL.md found")
        stats['skipped'] += 1
        return stats
    
    content = skill_md.read_text(encoding='utf-8')
    
    # Parse YAML frontmatter
    yaml_data = {}
    body = content
    if content.startswith('---\n'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                yaml_data = yaml.safe_load(parts[1])
                body = parts[2].strip()
            except yaml.YAMLError:
                body = content
    
    # Check for existing
    name = yaml_data.get('name', skill_dir.name)
    if SkillEngram.objects.filter(name=name, is_active=True).exists():
        stats['skipped'] += 1
        return stats
    
    # Create SkillEngram
    skill = SkillEngram.objects.create(
        name=name,
        description=yaml_data.get('description', '')[:200],
        category=yaml_data.get('category', ''),
        body=body,
        yaml_frontmatter=yaml_data,
    )
    stats['created'] += 1
    
    # Migrate attached files
    for subdir_name in ['scripts', 'templates', 'references', 'assets']:
        subdir = skill_dir / subdir_name
        if subdir.exists() and subdir.is_dir():
            type_map = {
                'scripts': 'script',
                'templates': 'template',
                'references': 'reference',
                'assets': 'asset',
            }
            for file in sorted(subdir.iterdir()):
                if file.is_file():
                    SkillFileAttachment.objects.create(
                        skill=skill,
                        file_type=type_map[subdir_name],
                        file_path=str(file.relative_to(skill_dir)),
                        file_content=file.read_text(encoding='utf-8', errors='replace'),
                    )
    
    # Embed
    _embed_skill(skill)
    
    return stats
```

**Migration command:** Wrap as a Django management command: `python manage.py migrate_skills_from_hermes`

---

## 6. File Changes Summary

| File | Action | Est. Lines |
|------|--------|-----------|
| `hippocampus/models.py` | ENHANCE (add SkillEngram + SkillFileAttachment) | ~60 |
| `hippocampus/migrations/XXXX_skill_engram.py` | NEW (auto-generated) | ~40 |
| `hippocampus/signals.py` | NEW (post-save embedding signal) | ~30 |
| `parietal_lobe/parietal_mcp/mcp_skill_manage.py` | NEW | ~300 |
| `parietal_lobe/parietal_mcp/mcp_skill_view.py` | NEW | ~60 |
| `parietal_lobe/parietal_mcp/mcp_skills_list.py` | NEW | ~30 |
| `scripts/migrate_hermes_skills.py` | NEW | ~200 |
| `hippocampus/tests/test_skill_engram.py` | NEW | ~150 |
| `parietal_lobe/tests/test_skills_tools.py` | NEW | ~120 |

**Total:** ~990 new lines + ~60 modified lines + auto-generated migration.

---

## 7. Acceptance Criteria

1. `SkillEngram` and `SkillFileAttachment` models exist and are queryable via Django ORM
2. Vector embeddings are generated on create (post-save signal or explicit call)
3. All 3 skill tools (manage, view, list) work through ParietalLobe pipeline
4. `mcp_skill_manage` supports all 6 actions: create, patch, edit, delete, write_file, remove_file
5. Hermes skills migration script runs successfully and creates correct records
6. Skills can be looked up by semantic similarity (vector search)
7. The `skills_index_addon` (Layer 3) works with SkillEngram records
8. Category filtering works in mcp_skills_list
9. Soft delete (is_active=False) hides skills from list but preserves data
10. File attachments are correctly created/retrieved for scripts, templates, references

---

## 8. Integration with Other Layers

- **Layer 3 (Identity Addons):** The `skills_index_addon` queries SkillEngram to build the compact skill catalog for system prompt injection. It uses `mcp_skills_list`-equivalent logic.
- **Layer 1 (Core MCP Tools):** The `mcp_skill_manage`, `mcp_skill_view`, and `mcp_skills_list` tools are part of the 10-tool suite in Layer 1. This plan defines their implementation; Layer 1 registers their ToolDefinitions.
- **Layer 5 feeds back into Layer 1:** Once skills are working, the existing Hermes skills (~30+) become immediately available through the Talos interface. The IdentityDisc can have skills enabled/disabled per persona.

---

*End of Layer 5 Plan*
