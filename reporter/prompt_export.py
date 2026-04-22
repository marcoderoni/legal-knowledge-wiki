"""
reporter/prompt_export.py
--------------------------
Exports the knowledge graph structure and gap analysis as ready-to-use
Claude prompts. Inspired by the "InfraNodus log" pattern from the video:
paste the exported prompt directly into Claude to guide gap-bridging analysis.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import date


PROMPT_HEADER = """# Legal Knowledge Graph — AI Research Prompts
Generated: {date}
Concepts: {n_concepts} | Connections: {n_connections} | Gaps: {n_gaps}

These prompts are ready to paste into Claude Code or any LLM.
Each prompt includes the underlying graph structure so the LLM can reason
about the knowledge gap — not just retrieve the most probable answer.

---
"""

GAP_PROMPT_TEMPLATE = """## Prompt {index}: Bridge gap between "{cluster_a}" and "{cluster_b}"

**Gap description:** {gap_description}

**Paste this prompt into Claude:**

```
I am working on a legal knowledge base. My knowledge graph shows a gap between
two clusters of concepts that should be better connected:

CLUSTER A — {cluster_a}
Concepts: {concepts_a}

CLUSTER B — {cluster_b}  
Concepts: {concepts_b}

Gap: {gap_description}

Graph structure (JSON):
{graph_structure}

Task: Review the concepts and connections above.
1. Identify the most legally significant relationship between these two clusters.
2. Propose 2-3 new concepts or principles that would bridge this gap.
3. Draft a concrete legal provision, clause, or policy recommendation that addresses this gap.
4. Suggest 1-2 source documents I should add to my knowledge base to develop this area further.

Base your analysis on the graph structure provided, not general knowledge alone.
```

---
"""

ISOLATED_PROMPT_TEMPLATE = """## Prompt {index}: Develop isolated concept "{concept}"

**Why it matters:** {rationale}

**Paste this prompt into Claude:**

```
I am building a legal knowledge base. The concept "{concept}" appears in my
knowledge graph but has very few connections to other concepts (currently: {connections}).

Definition I have: {definition}

Possible connections identified: {could_connect}

Task:
1. Explain why "{concept}" is legally significant in this context.
2. Identify which existing concepts it should be connected to and what the relationship is.
3. Draft a brief wiki article expansion that makes these connections explicit.
4. Suggest what type of source document would best develop this concept further.
```

---
"""

RESEARCH_PROMPT_TEMPLATE = """## Prompt {index}: Research question — {priority} priority

**Question:** {question}

**Paste this prompt into Claude:**

```
Research question for my legal knowledge base:

{question}

My current knowledge graph contains {n_concepts} concepts across these main areas:
{concept_summary}

Task:
1. Answer this research question based on established legal principles.
2. Identify which concepts in my knowledge base are most relevant.
3. Flag any areas where current law is unsettled or jurisdiction-dependent.
4. Suggest 2-3 follow-up questions that would deepen this analysis.
```

---
"""


def build_graph_structure_json(
    concepts: list[dict],
    connections: list[dict],
    relevant_names: list[str],
) -> str:
    """Build a compact JSON graph structure for embedding in prompts."""
    relevant = set(relevant_names)
    nodes = [
        {"id": c["name"], "type": c.get("type", "concept")}
        for c in concepts
        if c["name"] in relevant
    ]
    links = [
        {"s": l["source"], "t": l["target"], "r": l.get("relationship", "")}
        for l in connections
        if l.get("source") in relevant or l.get("target") in relevant
    ]
    return json.dumps({"nodes": nodes, "links": links}, ensure_ascii=False)


def _get_cluster_concepts(
    area: str, missing_concepts: list[str], all_concepts: list[dict]
) -> list[str]:
    """Find concepts related to an area by keyword matching."""
    area_lower = area.lower()
    matches = [
        c["name"] for c in all_concepts
        if area_lower in c["name"].lower()
        or area_lower in c.get("definition", "").lower()
    ]
    return list(set(matches + missing_concepts))[:8]


def export_prompts(
    concepts: list[dict],
    connections: list[dict],
    gaps: dict,
    output_path: Path,
) -> None:
    """Write a markdown file of ready-to-use Claude prompts from gap analysis."""
    n_gaps = (
        len(gaps.get("missing_definitions", []))
        + len(gaps.get("knowledge_gaps", []))
    )
    concept_summary = ", ".join(c["name"] for c in concepts[:20])

    lines = [
        PROMPT_HEADER.format(
            date=date.today().isoformat(),
            n_concepts=len(concepts),
            n_connections=len(connections),
            n_gaps=n_gaps,
        )
    ]

    idx = 1

    # 1. Knowledge gap bridge prompts
    for gap in gaps.get("knowledge_gaps", []):
        area = gap.get("area", "Unknown")
        missing = gap.get("missing_concepts", [])
        description = gap.get("description", "")

        # Split area into two clusters if possible (heuristic: split on " and " or " vs ")
        parts = re.split(r" and | vs | & ", area, maxsplit=1)
        cluster_a = parts[0].strip() if len(parts) > 1 else area
        cluster_b = parts[1].strip() if len(parts) > 1 else (missing[0] if missing else "related concepts")

        concepts_a = _get_cluster_concepts(cluster_a, [], concepts)
        concepts_b = _get_cluster_concepts(cluster_b, missing, concepts)
        relevant = list(set(concepts_a + concepts_b))

        graph_json = build_graph_structure_json(concepts, connections, relevant)

        lines.append(GAP_PROMPT_TEMPLATE.format(
            index=idx,
            cluster_a=cluster_a,
            cluster_b=cluster_b,
            gap_description=description,
            concepts_a=", ".join(concepts_a) or "not yet defined",
            concepts_b=", ".join(concepts_b) or "not yet defined",
            graph_structure=graph_json,
        ))
        idx += 1

    # 2. Isolated concept prompts
    for bridge in gaps.get("isolated_bridges", [])[:5]:
        concept_name = bridge.get("concept", "")
        concept_data = next((c for c in concepts if c["name"] == concept_name), {})
        conn_count = sum(
            1 for l in connections
            if l.get("source") == concept_name or l.get("target") == concept_name
        )
        lines.append(ISOLATED_PROMPT_TEMPLATE.format(
            index=idx,
            concept=concept_name,
            rationale=bridge.get("rationale", ""),
            connections=conn_count,
            definition=concept_data.get("definition", "Not yet defined"),
            could_connect=", ".join(bridge.get("could_connect", [])),
        ))
        idx += 1

    # 3. Research question prompts
    for q in gaps.get("research_questions", []):
        lines.append(RESEARCH_PROMPT_TEMPLATE.format(
            index=idx,
            priority=q.get("priority", "medium"),
            question=q.get("question", ""),
            n_concepts=len(concepts),
            concept_summary=concept_summary,
        ))
        idx += 1

    if idx == 1:
        lines.append("*No gaps or research questions identified in this run.*\n")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(lines), encoding="utf-8")


# Need re for cluster splitting
import re
