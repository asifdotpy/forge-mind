#!/usr/bin/env python3
"""
ForgeMind Knowledge Brain Sync Script (v3.0)
Recursively fetches and indexes the entire ForgeMind v3.0 Notion Knowledge Base
into a local embedded ChromaDB vector store following industry best practices:
- Context-enriched chunking (Contextual Retrieval with hierarchy breadcrumbs)
- Sliding-window semantic chunking with overlap
- Multi-dimensional metadata taxonomy (doc_type, hierarchy, section, version, etc.)
- Resilient tree traversal across all nested pages and databases
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional

import chromadb

ROOT_PAGE_ID = "3be6566c-d850-812b-910c-deb6500bf6c1"
PAGE_TITLE = "ForgeMind — Hierarchical Engineering Agent System"
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".brain_db")
COLLECTION_NAME = "forgemind_v3_core"
NOTION_API_VERSION = "2022-06-28"

# Max chunk characters and overlap
MAX_CHUNK_CHARS = 1200
CHUNK_OVERLAP_CHARS = 150
REQUEST_TIMEOUT = 12

def _load_dotenv() -> None:
    """Load a local `.env` file into os.environ.

    Lightweight substitute for python-dotenv (no external dependency).
    Defaults to the gitignored project-root `.env`; may be relocated with the
    NOTION_ENV_FILE environment variable. Existing environment variables always
    take precedence, and the file is skipped silently when absent.
    """
    env_path = os.environ.get("NOTION_ENV_FILE") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
    )
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"").strip()
                if key and key not in os.environ:
                    os.environ[key] = value
    except FileNotFoundError:
        pass

def get_notion_token() -> str:
    """Return the Notion integration token from the environment.

    The token MUST be provided via the NOTION_TOKEN environment variable
    (or a gitignored project-root `.env` file, which is auto-loaded). It must
    never be committed to the repository; calling code fails fast and loudly
    when it is absent.
    """
    _load_dotenv()
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        sys.exit(
            "Error: NOTION_TOKEN environment variable is not set.\n"
            "Set it before running the sync, e.g.:\n"
            "  cp .env.example .env   # then fill in your token\n"
            "  python scripts/sync_notion_brain.py\n"
            "or export it explicitly: export NOTION_TOKEN='ntn_<your_token>'"
        )
    return token

def get_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_API_VERSION,
        "Content-Type": "application/json"
    }

def fetch_block_children(block_id: str, token: str, retries: int = 3) -> List[Dict[str, Any]]:
    results = []
    cursor = None
    headers = get_headers(token)

    while True:
        url = f"https://api.notion.com/v1/blocks/{block_id}/children?page_size=100"
        if cursor:
            url += f"&start_cursor={cursor}"

        req = urllib.request.Request(url, headers=headers)
        success = False
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    results.extend(data.get("results", []))
                    if not data.get("has_more"):
                        return results
                    cursor = data.get("next_cursor")
                    success = True
                    break
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(2 ** attempt)
                    continue
                print(f"HTTP Error {e.code} fetching blocks for {block_id}: {e.reason}", file=sys.stderr, flush=True)
                break
            except Exception as e:
                time.sleep(1)
                continue
        if not success:
            break
    return results

def get_page_info(page_id: str, token: str) -> Dict[str, Any]:
    url = f"https://api.notion.com/v1/pages/{page_id}"
    req = urllib.request.Request(url, headers=get_headers(token))
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            title = ""
            props = data.get("properties", {})
            for _, v in props.items():
                if isinstance(v, dict) and v.get("type") == "title":
                    title = "".join([t.get("plain_text", "") for t in v.get("title", [])])
                    break
            return {
                "id": page_id,
                "title": title or "Untitled Page",
                "url": data.get("url", f"https://app.notion.com/p/{page_id.replace('-', '')}"),
                "public_url": data.get("public_url", "")
            }
    except Exception as e:
        return {
            "id": page_id,
            "title": "Untitled Page",
            "url": f"https://app.notion.com/p/{page_id.replace('-', '')}",
            "error": str(e)
        }

def classify_doc_type(title: str, hierarchy: str) -> str:
    title_lower = title.lower()
    hier_lower = hierarchy.lower()
    
    if title_lower.startswith("spec-") or "situation contract" in title_lower:
        return "specification"
    if title_lower.startswith("build-") or title_lower.startswith("adk-") or title_lower.startswith("imp-") or "execution plan" in title_lower:
        return "implementation_plan"
    if title_lower.startswith("adr-") or "architecture decision" in title_lower or "adr" in hier_lower:
        return "adr"
    if title_lower.startswith("eval-") or "evaluation" in title_lower or "evaluation lab" in hier_lower:
        return "evaluation"
    if title_lower.startswith("rv-") or "research" in title_lower or "research vault" in hier_lower:
        return "research"
    if title_lower.startswith("fixture-") or "scenario" in title_lower:
        return "fixture"
    if "agent registry" in title_lower or "agent registry" in hier_lower:
        return "agent_registry"
    if "failure" in title_lower or "failure library" in hier_lower:
        return "failure_lesson"
    if "daily" in title_lower or "log" in title_lower:
        return "daily_log"
    if "forgemind" in title_lower and "system" in title_lower:
        return "overview"
    return "documentation"

def extract_rich_text(rich_text_list: List[Dict[str, Any]]) -> str:
    if not rich_text_list:
        return ""
    return "".join([item.get("plain_text", "") for item in rich_text_list])

def block_to_markdown(block: Dict[str, Any], token: str, indent: int = 0, max_nesting: int = 2) -> str:
    b_type = block.get("type", "")
    prefix = "  " * indent
    text = ""
    has_children = block.get("has_children", False)
    block_id = block.get("id")

    if b_type in ["heading_1", "heading_2", "heading_3"]:
        level = 1 if b_type == "heading_1" else (2 if b_type == "heading_2" else 3)
        raw_text = extract_rich_text(block.get(b_type, {}).get("rich_text", []))
        text = f"\n{'#' * level} {raw_text}\n"

    elif b_type == "paragraph":
        raw_text = extract_rich_text(block.get("paragraph", {}).get("rich_text", []))
        if raw_text.strip():
            text = f"{prefix}{raw_text}\n"

    elif b_type == "bulleted_list_item":
        raw_text = extract_rich_text(block.get("bulleted_list_item", {}).get("rich_text", []))
        text = f"{prefix}- {raw_text}\n"

    elif b_type == "numbered_list_item":
        raw_text = extract_rich_text(block.get("numbered_list_item", {}).get("rich_text", []))
        text = f"{prefix}1. {raw_text}\n"

    elif b_type == "to_do":
        checked = "x" if block.get("to_do", {}).get("checked") else " "
        raw_text = extract_rich_text(block.get("to_do", {}).get("rich_text", []))
        text = f"{prefix}- [{checked}] {raw_text}\n"

    elif b_type == "quote":
        raw_text = extract_rich_text(block.get("quote", {}).get("rich_text", []))
        text = f"{prefix}> {raw_text}\n"

    elif b_type == "callout":
        raw_text = extract_rich_text(block.get("callout", {}).get("rich_text", []))
        icon = block.get("callout", {}).get("icon", {}).get("emoji", "💡")
        text = f"\n{prefix}> {icon} **Note:** {raw_text}\n"

    elif b_type == "code":
        lang = block.get("code", {}).get("language", "")
        raw_text = extract_rich_text(block.get("code", {}).get("rich_text", []))
        text = f"\n```{lang}\n{raw_text}\n```\n"

    elif b_type == "divider":
        text = "\n---\n"

    elif b_type == "table":
        rows = fetch_block_children(block_id, token)
        table_lines = []
        for i, row in enumerate(rows):
            if row.get("type") == "table_row":
                cells = [extract_rich_text(c).replace("\n", " ").strip() for c in row.get("table_row", {}).get("cells", [])]
                table_lines.append(f"| {' | '.join(cells)} |")
                if i == 0:
                    table_lines.append(f"| {' | '.join(['---'] * len(cells))} |")
        text = "\n" + "\n".join(table_lines) + "\n"
        has_children = False

    elif b_type == "table_row":
        cells = [extract_rich_text(cell).replace("\n", " ").strip() for cell in block.get("table_row", {}).get("cells", [])]
        text = f"| {' | '.join(cells)} |\n"

    elif b_type == "toggle":
        raw_text = extract_rich_text(block.get("toggle", {}).get("rich_text", []))
        text = f"\n<details><summary>{raw_text}</summary>\n"

    if has_children and indent < max_nesting and b_type not in ["child_page", "child_database"]:
        children = fetch_block_children(block_id, token)
        for child in children:
            text += block_to_markdown(child, token, indent + 1, max_nesting)
        if b_type == "toggle":
            text += "\n</details>\n"

    return text

def parse_blocks_to_sections(blocks: List[Dict[str, Any]], token: str, default_section: str = "Overview") -> List[Dict[str, Any]]:
    sections = []
    current_h1 = default_section
    current_h2 = ""
    current_h3 = ""
    current_content = []

    for block in blocks:
        b_type = block.get("type", "")

        if b_type in ["child_page", "child_database"]:
            continue

        if b_type == "heading_1":
            if current_content:
                section_title = " > ".join([s for s in [current_h1, current_h2, current_h3] if s])
                sections.append({
                    "section": section_title,
                    "content": "".join(current_content).strip()
                })
                current_content = []
            current_h1 = extract_rich_text(block.get("heading_1", {}).get("rich_text", [])) or "Heading 1"
            current_h2 = ""
            current_h3 = ""
            current_content.append(f"# {current_h1}\n\n")

        elif b_type == "heading_2":
            if current_content:
                section_title = " > ".join([s for s in [current_h1, current_h2, current_h3] if s])
                sections.append({
                    "section": section_title,
                    "content": "".join(current_content).strip()
                })
                current_content = []
            current_h2 = extract_rich_text(block.get("heading_2", {}).get("rich_text", [])) or "Heading 2"
            current_h3 = ""
            current_content.append(f"## {current_h2}\n\n")

        elif b_type == "heading_3":
            if current_content:
                section_title = " > ".join([s for s in [current_h1, current_h2, current_h3] if s])
                sections.append({
                    "section": section_title,
                    "content": "".join(current_content).strip()
                })
                current_content = []
            current_h3 = extract_rich_text(block.get("heading_3", {}).get("rich_text", [])) or "Heading 3"
            current_content.append(f"### {current_h3}\n\n")

        else:
            md = block_to_markdown(block, token)
            if md:
                current_content.append(md)

    if current_content:
        section_title = " > ".join([s for s in [current_h1, current_h2, current_h3] if s])
        sections.append({
            "section": section_title,
            "content": "".join(current_content).strip()
        })

    return [s for s in sections if s["content"].strip()]

def chunk_section_with_overlap(section: Dict[str, Any], page_title: str, hierarchy: str) -> List[Dict[str, Any]]:
    content = section["content"].strip()
    section_name = section["section"]
    breadcrumb = f"{hierarchy} > {section_name}"

    if len(content) <= MAX_CHUNK_CHARS:
        contextual_text = f"Document: {page_title}\nHierarchy: {breadcrumb}\nSection: {section_name}\n\n{content}"
        return [{
            "section": section_name,
            "raw_text": content,
            "text": contextual_text
        }]

    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    chunks = []
    curr_paras = []
    curr_len = 0

    for p in paragraphs:
        p_len = len(p)
        if curr_len + p_len > MAX_CHUNK_CHARS and curr_paras:
            raw_chunk_text = "\n\n".join(curr_paras)
            contextual_text = f"Document: {page_title}\nHierarchy: {breadcrumb}\nSection: {section_name}\n\n{raw_chunk_text}"
            chunks.append({
                "section": section_name,
                "raw_text": raw_chunk_text,
                "text": contextual_text
            })

            if len(curr_paras[-1]) <= CHUNK_OVERLAP_CHARS:
                curr_paras = [curr_paras[-1], p]
                curr_len = len(curr_paras[0]) + len(p)
            else:
                curr_paras = [p]
                curr_len = p_len
        else:
            curr_paras.append(p)
            curr_len += p_len

    if curr_paras:
        raw_chunk_text = "\n\n".join(curr_paras)
        contextual_text = f"Document: {page_title}\nHierarchy: {breadcrumb}\nSection: {section_name}\n\n{raw_chunk_text}"
        chunks.append({
            "section": section_name,
            "raw_text": raw_chunk_text,
            "text": contextual_text
        })

    return chunks

class NotionCrawler:
    def __init__(self, token: str):
        self.token = token
        self.pages_data = []
        self.visited_ids = set()

    def crawl_tree(self, page_id: str, parent_title: str = "", hierarchy_path: str = ""):
        if page_id in self.visited_ids:
            return
        self.visited_ids.add(page_id)

        info = get_page_info(page_id, self.token)
        title = info["title"]
        current_hierarchy = f"{hierarchy_path} > {title}" if hierarchy_path else title
        print(f"  📥 [{len(self.pages_data)+1:02d}] Fetching [{title}] ({page_id})", flush=True)

        blocks = fetch_block_children(page_id, self.token)
        doc_type = classify_doc_type(title, current_hierarchy)

        self.pages_data.append({
            "page_id": page_id,
            "page_title": title,
            "url": info["url"],
            "parent_title": parent_title or "Root",
            "hierarchy": current_hierarchy,
            "doc_type": doc_type,
            "blocks": blocks
        })

        for b in blocks:
            b_type = b.get("type")
            if b_type == "child_page":
                child_id = b.get("id")
                self.crawl_tree(child_id, parent_title=title, hierarchy_path=current_hierarchy)
            elif b_type == "child_database":
                db_id = b.get("id")
                db_title = b.get("child_database", {}).get("title", "Database")
                db_url = f"https://api.notion.com/v1/databases/{db_id}/query"
                body = json.dumps({"page_size": 100}).encode("utf-8")
                req = urllib.request.Request(db_url, data=body, headers=get_headers(self.token), method="POST")
                try:
                    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                        db_data = json.loads(resp.read().decode("utf-8"))
                        for row in db_data.get("results", []):
                            row_id = row.get("id")
                            self.crawl_tree(row_id, parent_title=f"{title} ({db_title})", hierarchy_path=f"{current_hierarchy} > {db_title}")
                except Exception as e:
                    print(f"    ⚠️ Error querying database {db_id}: {e}", file=sys.stderr, flush=True)

def main():
    token = get_notion_token()
    print("=" * 80, flush=True)
    print("🚀 Starting ForgeMind v3.0 Knowledge Brain Synchronization", flush=True)
    print(f"Root Page: {PAGE_TITLE} ({ROOT_PAGE_ID})", flush=True)
    print(f"Target DB: {DB_DIR} | Collection: {COLLECTION_NAME}", flush=True)
    print("=" * 80, flush=True)

    crawler = NotionCrawler(token)
    crawler.crawl_tree(ROOT_PAGE_ID)
    print(f"\n Crawled {len(crawler.pages_data)} total Notion pages from the ForgeMind tree.", flush=True)

    all_chunks = []
    sync_time_iso = datetime.now(timezone.utc).isoformat()

    print("\n Parsing pages into context-enriched semantic chunks...", flush=True)
    for page in crawler.pages_data:
        sections = parse_blocks_to_sections(page["blocks"], token, default_section="Overview")
        page_chunks = []
        for sec in sections:
            chunks = chunk_section_with_overlap(sec, page["page_title"], page["hierarchy"])
            for c in chunks:
                page_chunks.append({
                    "page_id": page["page_id"],
                    "page_title": page["page_title"],
                    "url": page["url"],
                    "parent_title": page["parent_title"],
                    "hierarchy": page["hierarchy"],
                    "doc_type": page["doc_type"],
                    "section": c["section"],
                    "raw_text": c["raw_text"],
                    "text": c["text"],
                    "char_count": len(c["text"]),
                    "synced_at": sync_time_iso,
                    "version": "3.0"
                })
        
        total_p_chunks = len(page_chunks)
        for idx, c in enumerate(page_chunks):
            c["chunk_index"] = idx + 1
            c["total_chunks_in_page"] = total_p_chunks
        
        all_chunks.extend(page_chunks)

    print(f" Generated {len(all_chunks)} context-enriched semantic chunks across {len(crawler.pages_data)} pages.", flush=True)

    os.makedirs(DB_DIR, exist_ok=True)
    client = chromadb.PersistentClient(path=DB_DIR)

    try:
        client.delete_collection(COLLECTION_NAME)
        print(f" Refreshed existing collection '{COLLECTION_NAME}'.", flush=True)
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={
            "description": "ForgeMind v3.0 Canonical Knowledge Base (Full Tree)",
            "version": "3.0",
            "synced_at": sync_time_iso,
            "total_pages": len(crawler.pages_data),
            "total_chunks": len(all_chunks)
        }
    )

    BATCH_SIZE = 100
    for i in range(0, len(all_chunks), BATCH_SIZE):
        batch = all_chunks[i:i+BATCH_SIZE]
        documents = [c["text"] for c in batch]
        metadatas = [{
            "page_id": c["page_id"],
            "page_title": c["page_title"],
            "url": c["url"],
            "parent_title": c["parent_title"],
            "hierarchy": c["hierarchy"],
            "doc_type": c["doc_type"],
            "section": c["section"],
            "chunk_index": c["chunk_index"],
            "total_chunks_in_page": c["total_chunks_in_page"],
            "char_count": c["char_count"],
            "synced_at": c["synced_at"],
            "version": c["version"]
        } for c in batch]
        ids = [f"forgemind_v3_{page_idx+1:04d}" for page_idx in range(i, i + len(batch))]

        collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        print(f"  Indexed batch {i // BATCH_SIZE + 1} ({len(batch)} chunks)...", flush=True)

    print("\n" + "=" * 80, flush=True)
    print(f" Successfully synchronized ForgeMind v3.0 Knowledge Brain!", flush=True)
    print(f"  • Total Pages Ingested: {len(crawler.pages_data)}", flush=True)
    print(f"  • Total Chunks Stored:   {collection.count()}", flush=True)
    print(f"  • Vector DB Location:    {DB_DIR}", flush=True)
    print(f"  • Collection Name:       {COLLECTION_NAME}", flush=True)
    print("=" * 80, flush=True)

if __name__ == "__main__":
    main()
