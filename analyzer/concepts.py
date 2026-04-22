"""
Extracts legal concepts, entities, obligations, risks and
regulatory references from document chunks via Claude API.
"""
from __future__ import annotations
import json
import re
from typing import Any

import anthropic


SYSTEM_PROMPT = """You are an expert legal knowledge engineer. Your task is to extract
structured legal knowledge from documents. Be precise, consistent, and thorough.
You must ALWAYS respond with valid JSON only — no preamble, no explanation, no markdown fences."""

EXTRACTION_PROMPT = """Analyse the following legal text and extract structured knowledge.

Respond with ONLY this JSON object — nothing before or after it:
{{
  "concepts": [
    {{"name": "string (2-5 words, title-case)", "definition": "string (1-2 sentences)", "type": "principle|term|standard|right|obligation|risk|entity|regulation", "importance": "high|medium|low"}}
  ],
  "connections": [
    {{"source": "concept name", "target": "concept name", "relationship": "string"}}
  ]
}}

Rules:
- Extract 5-20 concepts per chunk, prioritising legally significant ones
- Concept names must be consistent (same term = same name across all chunks)
- Only create connections between concepts that appear in THIS chunk
- Types: principle, term, standard, right, obligation, risk, entity, regulation

TEXT TO ANALYSE:
{text}"""


def _parse_json_response(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'\s*```\s*$', '', raw, flags=re.MULTILINE)
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    match = re.search(r'\{[\s\S]*\}', raw)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    if '"concepts"' in raw:
        candidate = raw if raw.startswith('{') else '{' + raw
        if not candidate.endswith('}'):
            candidate += '}'
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    return {"concepts": [], "connections": []}


def extract_concepts(text: str, client: anthropic.Anthropic, model: str, max_tokens: int) -> dict[str, Any]:
    prompt = EXTRACTION_PROMPT.format(text=text[:8000])
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )
    return _parse_json_response(response.content[0].text)


def merge_extractions(extractions: list[dict[str, Any]]) -> dict[str, Any]:
    concepts: dict[str, dict] = {}
    connections: list[dict] = []

    for extraction in extractions:
        for concept in extraction.get("concepts", []):
            name = concept.get("name", "").strip()
            if not name:
                continue
            if name not in concepts:
                concepts[name] = concept
            else:
                existing = concepts[name]
                if len(concept.get("definition", "")) > len(existing.get("definition", "")):
                    existing["definition"] = concept["definition"]
                importance_rank = {"high": 3, "medium": 2, "low": 1}
                if importance_rank.get(concept.get("importance", "low"), 1) > \
                   importance_rank.get(existing.get("importance", "low"), 1):
                    existing["importance"] = concept["importance"]

        for conn in extraction.get("connections", []):
            src = conn.get("source", "").strip()
            tgt = conn.get("target", "").strip()
            if src and tgt and src != tgt:
                connections.append(conn)

    return {"concepts": list(concepts.values()), "connections": connections}
