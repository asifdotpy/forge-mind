#!/usr/bin/env python3
"""
ForgeMind Knowledge Brain Query Interface (v3.0)
Query the local embedded ChromaDB knowledge store for ForgeMind v3.0 architectural context.
Supports semantic vector search, metadata filtering by doc_type, section, or page, and JSON output.
"""

import os
import sys
import json
import argparse
from typing import Optional, Dict, Any, List
import chromadb

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".brain_db")
COLLECTION_NAME = "forgemind_v3_core"

def query_brain(
    query_text: str,
    n_results: int = 4,
    doc_type: Optional[str] = None,
    page_filter: Optional[str] = None,
    as_json: bool = False
) -> List[Dict[str, Any]]:
    if not os.path.exists(DB_DIR):
        print(f"Error: Knowledge brain DB directory '{DB_DIR}' not found. Run scripts/sync_notion_brain.py first.", file=sys.stderr)
        sys.exit(1)

    client = chromadb.PersistentClient(path=DB_DIR)
    try:
        collection = client.get_collection(name=COLLECTION_NAME)
    except Exception as e:
        print(f"Error: Collection '{COLLECTION_NAME}' not found: {e}", file=sys.stderr)
        sys.exit(1)

    # Build metadata where filter
    where_filter = None
    if doc_type and page_filter:
        where_filter = {
            "$and": [
                {"doc_type": {"$eq": doc_type}},
                {"page_title": {"$eq": page_filter}}
            ]
        }
    elif doc_type:
        where_filter = {"doc_type": {"$eq": doc_type}}
    elif page_filter:
        where_filter = {"page_title": {"$eq": page_filter}}

    query_kwargs = {
        "query_texts": [query_text],
        "n_results": n_results
    }
    if where_filter:
        query_kwargs["where"] = where_filter

    results = collection.query(**query_kwargs)

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0] if "distances" in results and results["distances"] else [None] * len(documents)

    formatted_results = []
    for i, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances)):
        formatted_results.append({
            "rank": i + 1,
            "document": doc,
            "metadata": meta,
            "distance": dist,
            "similarity_score": round(1.0 / (1.0 + dist), 4) if dist is not None else None
        })

    if as_json:
        print(json.dumps({
            "query": query_text,
            "total_matches": len(formatted_results),
            "collection": COLLECTION_NAME,
            "results": formatted_results
        }, indent=2))
        return formatted_results

    filter_info = f" [Filter: doc_type='{doc_type}']" if doc_type else ""
    if page_filter:
        filter_info += f" [Filter: page='{page_filter}']"

    print(f"\n🔍 ForgeMind v3.0 Brain Query: \"{query_text}\"{filter_info}")
    print(f"================================================================================")
    
    if not formatted_results:
        print("No matching knowledge artifacts found.")
        print("================================================================================")
        return []

    for r in formatted_results:
        meta = r["metadata"]
        page_title = meta.get("page_title", "Unknown Page")
        section = meta.get("section", "Unknown Section")
        hierarchy = meta.get("hierarchy", page_title)
        doc_type_val = meta.get("doc_type", "doc")
        url = meta.get("url", "")
        dist_str = f"Distance: {r['distance']:.4f} (Score: {r['similarity_score']:.3f})" if r['distance'] is not None else ""

        print(f"\n[{r['rank']}] 📄 {page_title}  |  🏷️  {doc_type_val.upper()}  |  {dist_str}")
        print(f"📍 Breadcrumb: {hierarchy} > {section}")
        if url:
            print(f"🔗 Notion: {url}")
        print("-" * 80)
        # Strip header if already present in display for cleaner reading
        doc_body = r["document"].strip()
        print(doc_body)
        print("=" * 80)

    return formatted_results

def main():
    parser = argparse.ArgumentParser(description="Query ForgeMind v3.0 Knowledge Brain")
    parser.add_argument("query", type=str, help="Architectural question, contract field, or search term")
    parser.add_argument("-k", "--top-k", type=int, default=4, help="Number of top results to return (default: 4)")
    parser.add_argument("-t", "--doc-type", type=str, choices=[
        "specification", "implementation_plan", "adr", "research", "evaluation",
        "fixture", "agent_registry", "failure_lesson", "daily_log", "overview", "documentation"
    ], help="Filter results by document type")
    parser.add_argument("-p", "--page", type=str, help="Filter results by specific page title")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    query_brain(
        args.query,
        n_results=args.top_k,
        doc_type=args.doc_type,
        page_filter=args.page,
        as_json=args.json
    )

if __name__ == "__main__":
    main()
