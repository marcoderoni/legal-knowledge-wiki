"""
reporter/todo.py
-----------------
Generates prioritised to-do markdown files in todo/ based on gap analysis.
Three files: sources to add, concepts to develop, research questions to answer.
"""
from __future__ import annotations
from pathlib import Path
from datetime import date


def write_todos(
    concepts: list[dict],
    connections: list[dict],
    gaps: dict,
    todo_dir: Path,
) -> None:
    """Write three todo files to todo/."""
    todo_dir.mkdir(exist_ok=True)
    _write_sources_todo(gaps, todo_dir)
    _write_concepts_todo(concepts, connections, gaps, todo_dir)
    _write_research_todo(gaps, todo_dir)
    _write_todo_index(todo_dir)


def _write_sources_todo(gaps: dict, todo_dir: Path) -> None:
    """01_sources_to_add.md — what documents to ingest next."""
    lines = [
        "# Sources to Add\n",
        f"*Updated: {date.today().isoformat()}*\n\n",
        "Check off as you add documents to `sources/` and re-run `python main.py`.\n\n",
    ]

    # Derive suggested sources from gaps
    knowledge_gaps = gaps.get("knowledge_gaps", [])
    missing_defs = gaps.get("missing_definitions", [])

    if knowledge_gaps:
        lines.append("## 🔴 High priority — fill knowledge gaps\n")
        for gap in knowledge_gaps:
            area = gap.get("area", "Unknown area")
            desc = gap.get("description", "")
            missing = gap.get("missing_concepts", [])
            lines.append(f"- [ ] **{area}**: {desc[:80]}")
            if missing:
                lines.append(f"  - *Missing concepts:* {', '.join(missing[:4])}")
            lines.append(f"  - *Suggested:* add a regulatory text, guidance document, or playbook covering {area.lower()}")
            lines.append("")

    if missing_defs:
        lines.append("## 🟡 Medium priority — clarify undefined concepts\n")
        for m in missing_defs:
            concept = m.get("concept", "")
            reason = m.get("reason", "")
            lines.append(f"- [ ] **{concept}**: {reason[:80]}")
            lines.append(f"  - *Suggested:* find a source document that formally defines this term")
            lines.append("")

    lines.append("## ✅ Completed\n")
    lines.append("*(Move items here when ingested)*\n")

    (todo_dir / "01_sources_to_add.md").write_text("\n".join(lines), encoding="utf-8")


def _write_concepts_todo(
    concepts: list[dict],
    connections: list[dict],
    gaps: dict,
    todo_dir: Path,
) -> None:
    """02_concepts_to_develop.md — concepts that need more work."""
    # Find concepts with few connections
    conn_count: dict[str, int] = {}
    for c in connections:
        src, tgt = c.get("source", ""), c.get("target", "")
        conn_count[src] = conn_count.get(src, 0) + 1
        conn_count[tgt] = conn_count.get(tgt, 0) + 1

    isolated = sorted(
        [c for c in concepts if conn_count.get(c["name"], 0) <= 1],
        key=lambda x: {"high": 3, "medium": 2, "low": 1}.get(x.get("importance", "low"), 1),
        reverse=True,
    )[:20]

    bridge_candidates = gaps.get("isolated_bridges", [])

    lines = [
        "# Concepts to Develop\n",
        f"*Updated: {date.today().isoformat()}*\n\n",
        "These concepts are present in the knowledge base but need more connections or richer definitions.\n\n",
    ]

    if bridge_candidates:
        lines.append("## 🔴 Isolated concepts with bridge potential\n")
        for b in bridge_candidates:
            concept = b.get("concept", "")
            rationale = b.get("rationale", "")
            could_connect = b.get("could_connect", [])
            lines.append(f"- [ ] **{concept}**")
            lines.append(f"  - *Why:* {rationale[:100]}")
            if could_connect:
                lines.append(f"  - *Could connect to:* {', '.join(could_connect[:4])}")
            lines.append(f"  - *Action:* use the prompt in `output/graph_prompts.md` to bridge this gap")
            lines.append("")

    if isolated:
        lines.append("## 🟡 Low-connectivity concepts\n")
        for c in isolated:
            n_conn = conn_count.get(c["name"], 0)
            lines.append(f"- [ ] **{c['name']}** ({c.get('type', 'concept')}, {n_conn} connection{'s' if n_conn != 1 else ''})")
            if c.get("definition"):
                lines.append(f"  - *Definition:* {c['definition'][:80]}...")
            lines.append(f"  - *Action:* expand wiki article and add connections to related concepts")
            lines.append("")

    lines.append("## ✅ Completed\n")
    lines.append("*(Move items here when wiki article is expanded)*\n")

    (todo_dir / "02_concepts_to_develop.md").write_text("\n".join(lines), encoding="utf-8")


def _write_research_todo(gaps: dict, todo_dir: Path) -> None:
    """03_research_questions.md — open questions to answer."""
    questions = gaps.get("research_questions", [])

    lines = [
        "# Research Questions\n",
        f"*Updated: {date.today().isoformat()}*\n\n",
        "Open questions generated from gap analysis. ",
        "Use the prompts in `output/graph_prompts.md` to investigate these with Claude.\n\n",
    ]

    by_priority: dict[str, list] = {"high": [], "medium": [], "low": []}
    for q in questions:
        p = q.get("priority", "medium")
        by_priority.setdefault(p, []).append(q)

    priority_icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}

    for priority in ("high", "medium", "low"):
        qs = by_priority.get(priority, [])
        if not qs:
            continue
        lines.append(f"## {priority_icons[priority]} {priority.title()} priority\n")
        for q in qs:
            question = q.get("question", "")
            lines.append(f"- [ ] {question}")
            lines.append(f"  - *Action:* find the matching prompt in `output/graph_prompts.md` and paste into Claude Code")
            lines.append("")

    if not any(by_priority.values()):
        lines.append("*No research questions identified in this run.*\n")

    lines.append("## ✅ Answered\n")
    lines.append("*(Move items here with a brief answer summary)*\n")

    (todo_dir / "03_research_questions.md").write_text("\n".join(lines), encoding="utf-8")


def _write_todo_index(todo_dir: Path) -> None:
    """README.md in todo/ — quick index."""
    content = f"""# To-Do Index
*Updated: {date.today().isoformat()}*

| File | Purpose |
|------|---------|
| [01_sources_to_add.md](01_sources_to_add.md) | Documents to ingest to fill knowledge gaps |
| [02_concepts_to_develop.md](02_concepts_to_develop.md) | Wiki articles that need expansion or connections |
| [03_research_questions.md](03_research_questions.md) | Open questions to investigate with Claude |

## Workflow

1. Start with `03_research_questions.md` — use the graph prompts to answer priority questions
2. Use `01_sources_to_add.md` to identify new documents to ingest
3. After ingesting, re-run `python main.py --mode all` to update everything
4. Use `02_concepts_to_develop.md` to manually improve weak wiki articles

## Quick commands

```bash
# Full rebuild after adding new sources
python main.py --mode all

# Regenerate graph/todos without wiki (fast)
python main.py --mode graph --no-wiki

# Only export new prompts from saved data
python main.py --mode graph
```
"""
    (todo_dir / "README.md").write_text(content, encoding="utf-8")
