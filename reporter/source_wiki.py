"""
reporter/source_wiki.py
-----------------------
Generates a structured wiki page for each ingested source document.
Format: summary, key takeaways, evidence/data, quotes, relevant concepts, links.
"""
from __future__ import annotations
import re
from pathlib import Path
from datetime import date

import anthropic


SOURCE_PAGE_PROMPT = """You are a legal knowledge base author. Analyse this legal document and produce
a structured wiki source page for a legal professional.

Document name: {doc_name}
Document text (excerpt):
{text}

Write a markdown source page in EXACTLY this format — no extra sections:

# {doc_name}

**Type:** {doc_type}  
**Ingested:** {today}  
**Word count (approx):** {word_count}

## Summary
[3-4 sentences covering the document's purpose, scope and key legal significance]

## Key Takeaways
- [Most important legal point]
- [Second important point]
- [Third important point]
- [Fourth point if applicable]

## Evidence & Data
- [Specific thresholds, deadlines, penalties, figures mentioned — e.g. "72-hour breach notification", "€20M fine"]
- [Add only factual, citable items]

## Notable Provisions
> [Most legally significant clause or passage — keep under 40 words, paraphrase if needed]

> [Second notable provision if any]

## Relevant Concepts
[List as wikilinks: [[Concept One]], [[Concept Two]], ...]

## Gaps & Open Questions
- [What this document does NOT address that a legal professional would need]
- [Any ambiguity or conflict with other legal frameworks]

---
*Source: {doc_name} | {today}*"""

DOC_TYPE_MAP = {
    ".pdf": "PDF Document",
    ".docx": "Word Document",
    ".doc": "Word Document",
    ".txt": "Text File",
    ".md": "Markdown / Note",
}


def generate_source_page(
    doc_path: Path,
    text: str,
    concepts: list[dict],
    client: anthropic.Anthropic,
    model: str,
    max_tokens: int,
) -> str:
    """Generate a wiki source page for a single document."""
    # Get concepts most likely mentioned in this document
    concept_names = [c["name"] for c in concepts[:20]]
    word_count = len(text.split())
    excerpt = text[:6000]  # first ~6k chars for context

    prompt = SOURCE_PAGE_PROMPT.format(
        doc_name=doc_path.name,
        doc_type=DOC_TYPE_MAP.get(doc_path.suffix.lower(), "Document"),
        today=date.today().isoformat(),
        word_count=f"~{(word_count // 100) * 100}",
        text=excerpt,
    )

    # Append concepts hint
    if concept_names:
        prompt += f"\n\nConcepts identified in this document (use as [[wikilinks]] where appropriate):\n"
        prompt += ", ".join(concept_names)

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def write_source_pages(
    doc_texts: dict[str, str],   # {filename: full_text}
    doc_concepts: dict[str, list],  # {filename: [concepts]}
    output_dir: Path,
    client: anthropic.Anthropic,
    model: str,
    max_tokens: int,
    verbose: bool = True,
) -> None:
    """Generate and write source wiki pages for all ingested documents."""
    output_dir.mkdir(parents=True, exist_ok=True)
    docs = list(doc_texts.items())

    for i, (filename, text) in enumerate(docs):
        doc_path = Path(filename)
        safe_name = re.sub(r"[^\w\s-]", "", doc_path.stem).replace(" ", "_")
        out_path = output_dir / f"{safe_name}.md"

        if verbose:
            print(f"  [{i+1}/{len(docs)}] Source page: {filename}")

        concepts = doc_concepts.get(filename, [])
        page = generate_source_page(doc_path, text, concepts, client, model, max_tokens)
        out_path.write_text(page, encoding="utf-8")

    # Write sources index
    _write_sources_index(list(doc_texts.keys()), output_dir)


def _write_sources_index(filenames: list[str], output_dir: Path) -> None:
    lines = [
        "# Sources Index\n",
        f"*{len(filenames)} document(s) ingested — {date.today().isoformat()}*\n\n",
    ]
    for fn in sorted(filenames):
        safe = re.sub(r"[^\w\s-]", "", Path(fn).stem).replace(" ", "_")
        lines.append(f"- [{fn}]({safe}.md)")
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
