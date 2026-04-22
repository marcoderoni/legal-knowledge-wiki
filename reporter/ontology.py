"""
reporter/ontology.py
---------------------
Manages the .infranodus/ hidden folder — the "living memory" of the knowledge graph.
On each run, it loads the previous ontology state and merges new concepts and
connections incrementally, preserving history across runs.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import date
from typing import Any


ONTOLOGY_PATH_NAME = ".infranodus/ontology.json"
HISTORY_PATH_NAME = ".infranodus/history.jsonl"


def load_ontology(project_root: Path) -> dict[str, Any]:
    """Load previous ontology state, or return empty if first run."""
    path = project_root / ONTOLOGY_PATH_NAME
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "metadata": {"created": date.today().isoformat(), "runs": 0},
        "nodes": [],
        "links": [],
        "gaps": {},
        "source_count": 0,
    }


def merge_ontology(
    previous: dict[str, Any],
    concepts: list[dict],
    connections: list[dict],
    gaps: dict,
    source_count: int,
) -> dict[str, Any]:
    """
    Merge new extraction results into the existing ontology.
    - Concepts: add new ones; update definition/importance if improved
    - Connections: add new ones; deduplicate by (source, target) pair
    - Gaps: replace with latest (gaps evolve as knowledge grows)
    """
    # ── Merge nodes ────────────────────────────────────────────
    existing_nodes: dict[str, dict] = {n["id"]: n for n in previous.get("nodes", [])}
    importance_rank = {"high": 3, "medium": 2, "low": 1}

    for concept in concepts:
        name = concept["name"]
        node = {
            "id": name,
            "type": concept.get("type", "concept"),
            "importance": concept.get("importance", "medium"),
            "definition": concept.get("definition", ""),
        }
        if name not in existing_nodes:
            existing_nodes[name] = node
        else:
            prev = existing_nodes[name]
            # Upgrade definition if new one is longer/more detailed
            if len(node["definition"]) > len(prev.get("definition", "")):
                prev["definition"] = node["definition"]
            # Upgrade importance if higher
            if importance_rank.get(node["importance"], 1) > importance_rank.get(prev.get("importance", "low"), 1):
                prev["importance"] = node["importance"]

    # ── Merge links ────────────────────────────────────────────
    existing_links: dict[tuple, dict] = {}
    for link in previous.get("links", []):
        key = (link["source"], link["target"])
        existing_links[key] = link

    for conn in connections:
        src, tgt = conn.get("source", ""), conn.get("target", "")
        if not src or not tgt:
            continue
        # Normalise direction: always store alphabetically smaller first
        key = tuple(sorted([src, tgt]))
        if key not in existing_links:
            existing_links[key] = {
                "source": src,
                "target": tgt,
                "relationship": conn.get("relationship", "related to"),
            }

    # ── Build updated ontology ─────────────────────────────────
    meta = previous.get("metadata", {})
    meta["last_updated"] = date.today().isoformat()
    meta["runs"] = meta.get("runs", 0) + 1
    meta["concept_count"] = len(existing_nodes)
    meta["connection_count"] = len(existing_links)
    meta["source_count"] = source_count

    return {
        "metadata": meta,
        "nodes": list(existing_nodes.values()),
        "links": list(existing_links.values()),
        "gaps": gaps,
        "source_count": source_count,
    }


def save_ontology(ontology: dict[str, Any], project_root: Path) -> None:
    """Persist ontology to .infranodus/ontology.json."""
    infranodus_dir = project_root / ".infranodus"
    infranodus_dir.mkdir(exist_ok=True)

    # Save current state
    (project_root / ONTOLOGY_PATH_NAME).write_text(
        json.dumps(ontology, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Append a snapshot to history log (one JSON line per run)
    history_path = project_root / HISTORY_PATH_NAME
    snapshot = {
        "date": date.today().isoformat(),
        "run": ontology["metadata"].get("runs", 1),
        "concepts": ontology["metadata"].get("concept_count", 0),
        "connections": ontology["metadata"].get("connection_count", 0),
        "sources": ontology.get("source_count", 0),
        "gaps": len(ontology.get("gaps", {}).get("knowledge_gaps", [])),
    }
    with open(history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot) + "\n")


def write_ontology_readme(ontology: dict[str, Any], project_root: Path) -> None:
    """Write a human-readable summary of the current ontology state."""
    meta = ontology.get("metadata", {})
    nodes = ontology.get("nodes", [])
    gaps = ontology.get("gaps", {})

    # Type breakdown
    type_counts: dict[str, int] = {}
    for n in nodes:
        t = n.get("type", "concept")
        type_counts[t] = type_counts.get(t, 0) + 1

    type_lines = "\n".join(
        f"| {t} | {count} |"
        for t, count in sorted(type_counts.items(), key=lambda x: -x[1])
    )

    n_gaps = len(gaps.get("knowledge_gaps", [])) + len(gaps.get("missing_definitions", []))
    n_questions = len(gaps.get("research_questions", []))

    content = f"""# Ontology State — Living Memory

> Last updated: {meta.get('last_updated', 'unknown')} | Run #{meta.get('runs', 1)}

## Stats

| Metric | Value |
|--------|-------|
| Total concepts | {meta.get('concept_count', 0)} |
| Total connections | {meta.get('connection_count', 0)} |
| Source documents | {meta.get('source_count', 0)} |
| Knowledge gaps | {n_gaps} |
| Research questions | {n_questions} |

## Concept types

| Type | Count |
|------|-------|
{type_lines}

## History

See `.infranodus/history.jsonl` for per-run snapshots.

## Usage

Load `ontology.json` in Claude Code for structural context:

```
I am working on a legal knowledge base. Here is the current ontology state:
[paste contents of .infranodus/ontology.json]

Based on this structure, [your question here]
```

Or use the ready-made prompts in `output/graph_prompts.md`.
"""
    (project_root / ".infranodus" / "README.md").write_text(content, encoding="utf-8")
