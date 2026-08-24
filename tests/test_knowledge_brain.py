import os

import pytest

# ADR-009: chromadb is a dev-time Knowledge Brain dependency, never a runtime
# one. This module must skip cleanly — never fail or error — when either the
# chromadb package or the synced .brain_db/ index is absent (bare clone / CI).
chromadb = pytest.importorskip(
    "chromadb", reason="dev-time Knowledge Brain index (ADR-009)"
)

pytestmark = pytest.mark.brain

if not os.path.exists(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".brain_db")
):
    pytest.skip("no .brain_db; run scripts/sync_notion_brain.py", allow_module_level=True)

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".brain_db")
COLLECTION_NAME = "forgemind_v3_core"

def test_brain_collection_exists_and_populated():
    assert os.path.exists(DB_DIR), "ChromaDB directory .brain_db should exist."
    client = chromadb.PersistentClient(path=DB_DIR)
    collection = client.get_collection(COLLECTION_NAME)
    count = collection.count()
    # Entire ForgeMind v3.0 knowledge base across 30 pages generates well over 100 semantic chunks
    assert count >= 100, f"Expected at least 100 chunks across ForgeMind v3.0 pages, got {count}"

def test_brain_metadata_schema_integrity():
    client = chromadb.PersistentClient(path=DB_DIR)
    collection = client.get_collection(COLLECTION_NAME)
    sample = collection.get(limit=10, include=["metadatas", "documents"])
    
    assert len(sample["metadatas"]) > 0
    required_keys = {"page_id", "page_title", "hierarchy", "doc_type", "section", "version", "chunk_index"}
    
    for meta in sample["metadatas"]:
        for key in required_keys:
            assert key in meta, f"Metadata missing required key '{key}': {meta}"
        assert meta["version"] == "3.0"

def test_brain_semantic_retrieval_supervisor_dag():
    client = chromadb.PersistentClient(path=DB_DIR)
    collection = client.get_collection(COLLECTION_NAME)
    results = collection.query(
        query_texts=["5-tier DAG hierarchy Supervisor Domain Managers"],
        n_results=3
    )
    docs = results.get("documents", [[]])[0]
    assert len(docs) > 0
    combined = " ".join(docs)
    assert "Supervisor" in combined
    assert "Validator" in combined or "Manager" in combined or "DAG" in combined

def test_brain_spec_contract_retrieval():
    client = chromadb.PersistentClient(path=DB_DIR)
    collection = client.get_collection(COLLECTION_NAME)
    results = collection.query(
        query_texts=["Engineering Situation Contract SPEC-001 CoveragePlan EvidenceShard"],
        n_results=3,
        where={"doc_type": {"$eq": "specification"}}
    )
    docs = results.get("documents", [[]])[0]
    assert len(docs) > 0
    combined = " ".join(docs)
    assert "SPEC-001" in combined or "EvidenceShard" in combined or "CoveragePlan" in combined or "Engineering Situation" in combined

def test_brain_build_and_adk_plan_retrieval():
    client = chromadb.PersistentClient(path=DB_DIR)
    collection = client.get_collection(COLLECTION_NAME)
    results = collection.query(
        query_texts=["ADK 2 Workflow Runtime Implementation Plan ADK-001 BUILD-001"],
        n_results=3,
        where={"doc_type": {"$eq": "implementation_plan"}}
    )
    docs = results.get("documents", [[]])[0]
    assert len(docs) > 0
    combined = " ".join(docs)
    assert "ADK" in combined or "BUILD" in combined or "Workflow" in combined
