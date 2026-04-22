"""
Generates markdown wiki articles for each concept.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from datetime import date

import anthropic


WIKI_ARTICLE_PROMPT = """You are a legal knowledge base author writing a concise, accurate wiki article.

Write a markdown wiki article for the legal concept: **{name}**

Available information:
- Type: {type}
- Definition: {definition}
- Related concepts: {related}
- Source context: {source_context}

Write the article in this exact format (do NOT add extra sections):

# {name}

> {one_line_summary}

## Definition
{clear_definition}

## Legal Context
{legal_context_2_3_sentences}

## Key Considerations
- {bullet_1}
- {bullet_2}
- {bullet_3}

## Related Concepts
{related_links_as_wikilinks}

---
*Type: {type} | Last updated: {date}*"""


def generate_article(
    concept: dict,
    related: list[dict],
    connections: list[dict],
    client: anthropic.Anthropic,
    model: str,
    max_tokens: int
) -> str:
    """Generate a wiki article for a single concept."""
    related_names = [r["name"] for r in related[:8]]
    
    # Find relationships involving this concept
    relevant_conns = [
        c for c in connections
        if c.get("source") == concept["name"] or c.get("target") == concept["name"]
    ][:6]
    source_context = "; ".join(
        f"{c['source']} {c['relationship']} {c['target']}"
        for c in relevant_conns
    ) or "No specific context"
    
    prompt = WIKI_ARTICLE_PROMPT.format(
        name=concept["name"],
        type=concept.get("type", "concept"),
        definition=concept.get("definition", "Definition not available"),
        related=", ".join(related_names) or "None identified",
        source_context=source_context,
        date=date.today().isoformat(),
        one_line_summary=concept.get("definition", "")[:100],
        clear_definition="",
        legal_context_2_3_sentences="",
        legal_context="",
        bullet_1="", bullet_2="", bullet_3="",
        related_links_as_wikilinks=""
    )
    
    # Cleaner prompt — just instruct Claude directly
    prompt = f"""Write a concise markdown wiki article for the legal concept: **{concept["name"]}**

Type: {concept.get("type", "concept")}
Definition: {concept.get("definition", "N/A")}
Related concepts: {", ".join(related_names) or "None"}
Relationships: {source_context}

Format:
# {concept["name"]}

> [one-line summary]

## Definition
[2-3 sentences]

## Legal Context  
[2-3 sentences on practical/regulatory significance]

## Key Considerations
- [point 1]
- [point 2]  
- [point 3]

## Related Concepts
{" ".join(f"[[{r}]]" for r in related_names)}

---
*Type: {concept.get("type", "concept")} | {date.today().isoformat()}*"""

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text.strip()


def write_articles(
    concepts: list[dict],
    connections: list[dict],
    output_dir: Path,
    client: anthropic.Anthropic,
    model: str,
    max_tokens: int,
    verbose: bool = True
) -> None:
    """Generate and write wiki articles for all concepts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Build adjacency for related concepts
    adjacency: dict[str, set[str]] = {c["name"]: set() for c in concepts}
    for conn in connections:
        src, tgt = conn.get("source", ""), conn.get("target", "")
        if src in adjacency:
            adjacency[src].add(tgt)
        if tgt in adjacency:
            adjacency[tgt].add(src)
    
    concept_map = {c["name"]: c for c in concepts}
    
    for i, concept in enumerate(concepts):
        name = concept["name"]
        safe_name = re.sub(r'[^\w\s-]', '', name).replace(' ', '_')
        out_path = output_dir / f"{safe_name}.md"
        
        if verbose:
            print(f"  [{i+1}/{len(concepts)}] Writing wiki: {name}")
        
        related = [
            concept_map[r] for r in adjacency.get(name, set())
            if r in concept_map
        ]
        
        article = generate_article(concept, related, connections, client, model, max_tokens)
        out_path.write_text(article, encoding="utf-8")


def write_index(concepts: list[dict], connections: list[dict], output_dir: Path) -> None:
    """Write a README index of all wiki articles."""
    by_type: dict[str, list[dict]] = {}
    for c in concepts:
        t = c.get("type", "concept")
        by_type.setdefault(t, []).append(c)
    
    lines = [
        "# Legal Knowledge Wiki — Index\n",
        f"*{len(concepts)} concepts | {len(connections)} connections | Generated {date.today().isoformat()}*\n\n"
    ]
    
    type_icons = {
        "regulation": "📜", "principle": "⚖️", "obligation": "📋",
        "right": "🛡️", "risk": "⚠️", "term": "📖",
        "standard": "✅", "entity": "🏛️", "concept": "💡"
    }
    
    for t, items in sorted(by_type.items()):
        icon = type_icons.get(t, "💡")
        lines.append(f"## {icon} {t.title()}s\n")
        for c in sorted(items, key=lambda x: x["name"]):
            safe = re.sub(r'[^\w\s-]', '', c["name"]).replace(' ', '_')
            lines.append(f"- [{c['name']}]({safe}.md) — {c.get('definition', '')[:60]}...")
        lines.append("")
    
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
