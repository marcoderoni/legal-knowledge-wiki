"""
Cross-document connection mapping and gap analysis via Claude API.
"""
from __future__ import annotations
import json
import re
from typing import Any

import anthropic


CROSS_DOC_PROMPT = """You are a legal knowledge graph expert.

Given this list of legal concepts extracted from multiple documents, identify
ADDITIONAL meaningful connections between them that were not captured per-document.

Concepts:
{concepts_list}

Return ONLY valid JSON (no markdown):
{{
  "connections": [
    {{"source": "concept name", "target": "concept name", "relationship": "string"}}
  ]
}}

Focus on:
- Hierarchical relationships (e.g. "GDPR" governs "Personal Data Processing")
- Dependencies (e.g. "Data Transfer" requires "Adequacy Decision")
- Conflicts (e.g. "Broad IP Assignment" conflicts with "Employee Rights")
- Implementations (e.g. "Privacy by Design" implements "Data Minimisation")

Only include connections between concepts that are in the provided list.
Generate 10-30 high-quality connections."""

GAP_ANALYSIS_PROMPT = """You are an expert legal knowledge auditor.

Analyse this knowledge graph of legal concepts and their connections.

Concepts ({n_concepts} total):
{concepts_summary}

Isolated or weakly-connected concepts (few connections):
{isolated_concepts}

Identify knowledge gaps and produce a structured gap analysis.

Return ONLY valid JSON (no markdown):
{{
  "missing_definitions": [
    {{"concept": "string", "reason": "string"}}
  ],
  "knowledge_gaps": [
    {{"area": "string", "description": "string", "missing_concepts": ["string"]}}
  ],
  "research_questions": [
    {{"question": "string", "priority": "high|medium|low"}}
  ],
  "isolated_bridges": [
    {{"concept": "string", "could_connect": ["string"], "rationale": "string"}}
  ]
}}"""


def build_cross_connections(
    concepts: list[dict],
    client: anthropic.Anthropic,
    model: str,
    max_tokens: int
) -> list[dict]:
    """Ask Claude to find cross-document connections between all concepts."""
    concept_names = [c["name"] for c in concepts]
    # Limit to 80 most important to avoid token overflow
    important = [c for c in concepts if c.get("importance") == "high"][:40]
    medium = [c for c in concepts if c.get("importance") == "medium"][:30]
    rest = [c for c in concepts if c.get("importance") == "low"][:10]
    selected = important + medium + rest
    
    concepts_list = "\n".join(
        f"- {c['name']} ({c.get('type', 'concept')}): {c.get('definition', '')[:80]}"
        for c in selected
    )
    
    prompt = CROSS_DOC_PROMPT.format(concepts_list=concepts_list)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    
    raw = response.content[0].text.strip()
    raw = re.sub(r'^```json\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    
    try:
        data = json.loads(raw)
        # Filter to only valid concept names
        valid = set(concept_names)
        return [
            c for c in data.get("connections", [])
            if c.get("source") in valid and c.get("target") in valid
        ]
    except (json.JSONDecodeError, KeyError):
        return []


def analyse_gaps(
    concepts: list[dict],
    connections: list[dict],
    client: anthropic.Anthropic,
    model: str,
    max_tokens: int
) -> dict[str, Any]:
    """Generate a structured gap analysis of the knowledge graph."""
    # Find concepts with few connections
    connection_count: dict[str, int] = {}
    for conn in connections:
        connection_count[conn.get("source", "")] = connection_count.get(conn.get("source", ""), 0) + 1
        connection_count[conn.get("target", "")] = connection_count.get(conn.get("target", ""), 0) + 1
    
    isolated = [
        c for c in concepts
        if connection_count.get(c["name"], 0) <= 1
    ][:20]
    
    concepts_summary = "\n".join(
        f"- {c['name']} ({c.get('type', '?')}, connections: {connection_count.get(c['name'], 0)})"
        for c in concepts[:60]
    )
    isolated_list = "\n".join(f"- {c['name']}: {c.get('definition', '')[:60]}" for c in isolated)
    
    prompt = GAP_ANALYSIS_PROMPT.format(
        n_concepts=len(concepts),
        concepts_summary=concepts_summary,
        isolated_concepts=isolated_list or "None identified"
    )
    
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    
    raw = response.content[0].text.strip()
    raw = re.sub(r'^```json\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "missing_definitions": [],
            "knowledge_gaps": [],
            "research_questions": [],
            "isolated_bridges": []
        }
