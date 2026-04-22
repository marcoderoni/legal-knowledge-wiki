#!/usr/bin/env python3
"""
legal-knowledge-wiki v2
=======================
Ingest legal documents → extract concepts via Claude API →
build a knowledge graph → generate wiki articles, source pages,
interactive HTML visualisation, gap prompts, project docs, todos,
and an incremental living ontology in .infranodus/.

Usage:
  python main.py                          # full pipeline
  python main.py --sources path/to/docs   # custom sources folder
  python main.py --mode extract           # only extraction phase
  python main.py --mode graph             # regenerate graph/prompts/todos from saved data
  python main.py --mode wiki              # regenerate wiki articles from saved data
  python main.py --mode all               # full pipeline (default)
  python main.py --no-wiki                # skip wiki article generation (faster)
  python main.py --no-source-pages        # skip source wiki pages
  python main.py --no-browser             # don't auto-open browser
"""

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path

import anthropic
import yaml
from colorama import Fore, Style, init

init(autoreset=True)

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config" / "settings.yaml"
SOURCES_DIR = HERE / "sources"
WIKI_DIR = HERE / "wiki"
WIKI_SOURCES_DIR = HERE / "wiki" / "sources"
CONCEPTS_DIR = HERE / "concepts"
CONNECTIONS_DIR = HERE / "connections"
GAPS_DIR = HERE / "gaps"
OUTPUT_DIR = HERE / "output"
TODO_DIR = HERE / "todo"
INFRANODUS_DIR = HERE / ".infranodus"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def banner():
    print(f"\n{Fore.YELLOW}⚖  Legal Knowledge Wiki  v2{Style.RESET_ALL}")
    print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}\n")


def info(msg):  print(f"{Fore.CYAN}  ➤  {msg}{Style.RESET_ALL}")
def ok(msg):    print(f"{Fore.GREEN}  ✓  {msg}{Style.RESET_ALL}")
def warn(msg):  print(f"{Fore.YELLOW}  ⚠  {msg}{Style.RESET_ALL}")
def err(msg):   print(f"{Fore.RED}  ✗  {msg}{Style.RESET_ALL}")
def section(msg): print(f"\n{Fore.MAGENTA}  ── {msg} ──{Style.RESET_ALL}")


# ── Phase 1: Extraction ────────────────────────────────────────────────────────

def run_extraction(
    sources_dir: Path,
    config: dict,
    client: anthropic.Anthropic,
) -> tuple[dict, dict[str, str], dict[str, list]]:
    """
    Extract concepts from all documents.
    Returns: (merged_extraction, doc_texts, doc_concepts)
    """
    from extractor import extract, chunk, clean
    from analyzer import extract_concepts, merge_extractions

    model = config["anthropic"]["model"]
    max_tokens = config["anthropic"]["max_tokens"]
    chunk_size = config["extraction"]["max_chunk_size"]
    overlap = config["extraction"]["overlap"]

    supported = {".pdf", ".docx", ".doc", ".txt", ".md"}
    files = [f for f in sources_dir.iterdir() if f.suffix.lower() in supported]

    if not files:
        err(f"No supported documents found in {sources_dir}")
        err("Add PDF, DOCX, TXT or MD files to the sources/ folder and retry.")
        sys.exit(1)

    info(f"Found {len(files)} document(s) to process")

    all_extractions = []
    doc_texts: dict[str, str] = {}
    doc_concepts: dict[str, list] = {}

    for i, doc_path in enumerate(files):
        info(f"[{i+1}/{len(files)}] Extracting: {doc_path.name}")
        try:
            text = extract(doc_path)
            text = clean(text)
            doc_texts[doc_path.name] = text

            chunks = chunk(text, max_size=chunk_size, overlap=overlap)
            info(f"  → {len(chunks)} chunk(s)")

            doc_extractions = []
            for j, c in enumerate(chunks):
                info(f"  → Analysing chunk {j+1}/{len(chunks)}...")
                extraction = extract_concepts(c, client, model, max_tokens)
                doc_extractions.append(extraction)

            merged_doc = merge_extractions(doc_extractions)
            doc_concepts[doc_path.name] = merged_doc["concepts"]
            ok(f"  {len(merged_doc['concepts'])} concepts | {len(merged_doc['connections'])} connections")
            all_extractions.append(merged_doc)

            # Save per-document extraction
            CONCEPTS_DIR.mkdir(exist_ok=True)
            safe_name = doc_path.stem.replace(" ", "_")
            (CONCEPTS_DIR / f"{safe_name}.json").write_text(
                json.dumps(merged_doc, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            warn(f"Failed to process {doc_path.name}: {e}")
            continue

    global_merged = merge_extractions(all_extractions)
    ok(f"\nTotal: {len(global_merged['concepts'])} concepts across all documents")
    return global_merged, doc_texts, doc_concepts


# ── Phase 2: Connections + Gaps ────────────────────────────────────────────────

def run_connections_and_gaps(
    merged: dict,
    config: dict,
    client: anthropic.Anthropic,
) -> tuple[list, dict]:
    from analyzer import build_cross_connections, analyse_gaps

    model = config["anthropic"]["model"]
    max_tokens = config["anthropic"]["max_tokens"]

    info("Building cross-document connections...")
    extra = build_cross_connections(merged["concepts"], client, model, max_tokens)
    all_connections = merged["connections"] + extra
    ok(f"Total connections: {len(all_connections)}")

    info("Running gap analysis...")
    gaps = analyse_gaps(merged["concepts"], all_connections, client, model, max_tokens)
    n_gaps = len(gaps.get("missing_definitions", [])) + len(gaps.get("knowledge_gaps", []))
    ok(f"{n_gaps} gap(s) | {len(gaps.get('research_questions', []))} research question(s)")

    CONNECTIONS_DIR.mkdir(exist_ok=True)
    GAPS_DIR.mkdir(exist_ok=True)
    (CONNECTIONS_DIR / "all_connections.json").write_text(
        json.dumps(all_connections, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (GAPS_DIR / "gap_analysis.json").write_text(
        json.dumps(gaps, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return all_connections, gaps


# ── Phase 3: Source wiki pages ─────────────────────────────────────────────────

def run_source_pages(
    doc_texts: dict[str, str],
    doc_concepts: dict[str, list],
    config: dict,
    client: anthropic.Anthropic,
) -> None:
    from reporter.source_wiki import write_source_pages

    model = config["anthropic"]["model"]
    max_tokens = config["anthropic"]["max_tokens"]

    WIKI_SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    info(f"Generating {len(doc_texts)} source wiki page(s)...")
    write_source_pages(doc_texts, doc_concepts, WIKI_SOURCES_DIR, client, model, max_tokens)
    ok(f"Source pages written to {WIKI_SOURCES_DIR}/")


# ── Phase 4: Concept wiki articles ────────────────────────────────────────────

def run_wiki(
    concepts: list,
    connections: list,
    config: dict,
    client: anthropic.Anthropic,
) -> None:
    from reporter.wiki import write_articles, write_index

    model = config["anthropic"]["model"]
    max_tokens = config["anthropic"]["max_tokens"]

    WIKI_DIR.mkdir(exist_ok=True)
    info(f"Generating {len(concepts)} concept wiki articles...")
    write_articles(concepts, connections, WIKI_DIR, client, model, max_tokens)
    write_index(concepts, connections, WIKI_DIR)
    ok(f"Wiki written to {WIKI_DIR}/")


# ── Phase 5: Graph + prompts + todos + ontology + project docs ────────────────

def run_outputs(
    concepts: list,
    connections: list,
    gaps: dict,
    source_count: int,
    config: dict,
) -> Path:
    from reporter.visualizer import build_graph_data, generate_html
    from reporter.prompt_export import export_prompts
    from reporter.todo import write_todos
    from reporter.ontology import load_ontology, merge_ontology, save_ontology, write_ontology_readme
    from reporter.project_docs import write_claude_md, write_agents_md

    max_nodes = config["graph"]["max_nodes"]
    title = config["output"]["graph_title"]

    # ── 5a. HTML graph
    sorted_concepts = sorted(
        concepts,
        key=lambda c: {"high": 3, "medium": 2, "low": 1}.get(c.get("importance", "low"), 1),
        reverse=True,
    )[:max_nodes]

    info(f"Building HTML knowledge graph ({len(sorted_concepts)} nodes)...")
    graph_data = build_graph_data(sorted_concepts, connections, gaps)
    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / "knowledge_graph.html"
    generate_html(graph_data, out_path, title)
    ok(f"Graph → {out_path}")

    # ── 5b. Gap prompts
    info("Exporting gap-bridge prompts...")
    prompts_path = OUTPUT_DIR / "graph_prompts.md"
    export_prompts(concepts, connections, gaps, prompts_path)
    ok(f"Prompts → {prompts_path}")

    # ── 5c. To-do lists
    info("Generating to-do lists...")
    write_todos(concepts, connections, gaps, TODO_DIR)
    ok(f"Todos → {TODO_DIR}/")

    # ── 5d. Incremental ontology
    info("Updating .infranodus/ ontology...")
    previous = load_ontology(HERE)
    updated = merge_ontology(previous, concepts, connections, gaps, source_count)
    save_ontology(updated, HERE)
    write_ontology_readme(updated, HERE)
    runs = updated["metadata"].get("runs", 1)
    ok(f"Ontology → .infranodus/ontology.json (run #{runs}, "
       f"{updated['metadata'].get('concept_count', 0)} concepts, "
       f"{updated['metadata'].get('connection_count', 0)} connections)")

    # ── 5e. CLAUDE.md + agents.md
    info("Writing CLAUDE.md and agents.md...")
    write_claude_md(concepts, gaps, HERE)
    write_agents_md(HERE)
    ok(f"CLAUDE.md + agents.md written to project root")

    return out_path


# ── Load saved data ────────────────────────────────────────────────────────────

def load_saved_data() -> tuple[list, list, dict]:
    concept_files = list(CONCEPTS_DIR.glob("*.json")) if CONCEPTS_DIR.exists() else []
    all_extractions = []
    for f in concept_files:
        data = json.loads(f.read_text(encoding="utf-8"))
        all_extractions.append(data)

    from analyzer import merge_extractions
    merged = merge_extractions(all_extractions) if all_extractions else {"concepts": [], "connections": []}

    conn_path = CONNECTIONS_DIR / "all_connections.json"
    connections = json.loads(conn_path.read_text(encoding="utf-8")) if conn_path.exists() else []

    gaps_path = GAPS_DIR / "gap_analysis.json"
    gaps = json.loads(gaps_path.read_text(encoding="utf-8")) if gaps_path.exists() else {}

    return merged["concepts"], connections, gaps


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Legal Knowledge Wiki v2")
    parser.add_argument("--sources", type=Path, default=SOURCES_DIR)
    parser.add_argument("--mode", choices=["all", "extract", "graph", "wiki"], default="all")
    parser.add_argument("--no-wiki", action="store_true")
    parser.add_argument("--no-source-pages", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    banner()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        err("ANTHROPIC_API_KEY not set. Add it to your .env file.")
        sys.exit(1)

    config = load_config()
    client = anthropic.Anthropic(api_key=api_key)

    doc_texts: dict[str, str] = {}
    doc_concepts: dict[str, list] = {}

    if args.mode in ("all", "extract"):
        section("Phase 1 — Extract")
        merged, doc_texts, doc_concepts = run_extraction(args.sources, config, client)

        section("Phase 2 — Connect + Gap analysis")
        connections, gaps = run_connections_and_gaps(merged, config, client)
        concepts = merged["concepts"]

    else:
        info("Loading saved extraction data...")
        concepts, connections, gaps = load_saved_data()
        if not concepts:
            err("No saved data found. Run with --mode all first.")
            sys.exit(1)
        ok(f"Loaded {len(concepts)} concepts, {len(connections)} connections")

    source_count = len(list(args.sources.iterdir())) if args.sources.exists() else 0

    if args.mode in ("all", "extract") and not args.no_source_pages and doc_texts:
        section("Phase 3 — Source wiki pages")
        run_source_pages(doc_texts, doc_concepts, config, client)

    if args.mode in ("all", "wiki") and not args.no_wiki:
        section("Phase 4 — Concept wiki articles")
        run_wiki(concepts, connections, config, client)

    section("Phase 5 — Graph, prompts, todos, ontology, project docs")
    out_path = run_outputs(concepts, connections, gaps, source_count, config)

    if not args.no_browser and config["output"].get("open_browser", True):
        webbrowser.open(out_path.resolve().as_uri())

    print(f"\n{Fore.GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
    print(f"{Fore.GREEN}  Done.{Style.RESET_ALL}")
    print(f"  Graph      → {OUTPUT_DIR}/knowledge_graph.html")
    print(f"  Prompts    → {OUTPUT_DIR}/graph_prompts.md")
    print(f"  Todos      → {TODO_DIR}/")
    print(f"  Ontology   → .infranodus/ontology.json")
    if not args.no_source_pages:
        print(f"  Sources    → {WIKI_SOURCES_DIR}/")
    if not args.no_wiki:
        print(f"  Wiki       → {WIKI_DIR}/")
    print(f"  Context    → CLAUDE.md + agents.md\n")


if __name__ == "__main__":
    env_path = HERE / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    main()
