#!/usr/bin/env python3
"""
ForgeMind Notion Boundary Definition
=====================================
This module defines the authoritative boundary for ForgeMind's Notion Knowledge Base.
All sync and query operations MUST respect this boundary.

Boundary Rule: Only pages that are descendants of the ForgeMind Root Page
(3be6566c-d850-812b-910c-deb6500bf6c1) are in scope. Any page outside this
tree is out of bounds and MUST NOT be accessed, indexed, or modified.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Set

# =============================================================================
# ROOT PAGE
# =============================================================================

FORGEMIND_ROOT_PAGE_ID = "3be6566c-d850-812b-910c-deb6500bf6c1"
FORGEMIND_ROOT_PAGE_TITLE = "ForgeMind — Hierarchical Engineering Agent System"

# =============================================================================
# DIRECT CHILDREN (Tier 1 — Section Hubs)
# =============================================================================

TIER_1_CHILDREN = [
    {"title": "Research Vault", "id": "3be6566c-d850-814d-8ef3-d3b369d55744"},
    {"title": "Agent Registry", "id": "3be6566c-d850-8102-b3e8-ebd275956f3f"},
    {"title": "Architecture Decision Records", "id": "3be6566c-d850-81dc-bfaa-d630d203d3d6"},
    {"title": "Engineering Knowledge Model", "id": "3be6566c-d850-816e-8d72-f1bcccade9f2"},
    {"title": "Evaluation Lab", "id": "3be6566c-d850-8170-abeb-f24cf93525e4"},
    {"title": "Failure Library", "id": "3be6566c-d850-816f-8b60-f77827c9ad8c"},
    {"title": "Daily Hackathon Log", "id": "3be6566c-d850-8154-9db9-f217ccfb556e"},
    {"title": "Demo & Submission Center", "id": "3be6566c-d850-8134-a6cf-e23c8210af3b"},
    {"title": "Idea Parking Lot", "id": "3be6566c-d850-8161-8a9d-e6cfacd31c06"},
    {"title": "Execution Plan", "id": "3bf6566c-d850-81e4-82ad-dadad4861854"},
    {"title": "SPEC-001 — Engineering Situation Contract", "id": "3c06566c-d850-810c-b363-d68f5e26cc91"},
    {"title": "FIXTURE-001 — Change-to-Incident Canonical Demo Scenario", "id": "3c06566c-d850-812b-90c9-d832f3785458"},
    {"title": "Evaluation Lab — Contract, Protocol & Regression Loop", "id": "3c06566c-d850-81d4-9b31-cb1c64ef1059"},
    {"title": "EVAL-001 to EVAL-009 — Initial Evaluation Specifications", "id": "3c06566c-d850-8196-8a96-cfc1ee4046c8"},
    {"title": "Failure → Regression Workflow", "id": "3c06566c-d850-8123-86fb-d25995393dfd"},
    {"title": "IMP-001 — ForgeMind Google Cloud Implementation Mapping", "id": "3c06566c-d850-813c-8aa9-c06741e7e4f1"},
    {"title": "ADR-002 — Single Deployable MVP with Replaceable Infrastructure Boundaries", "id": "3c06566c-d850-810e-b327-c626d08c692f"},
    {"title": "BUILD-001 — ForgeMind MVP Implementation Plan", "id": "3c06566c-d850-8119-a28d-ceb5f8edb038"},
    {"title": "⚙️ ADK-001 — ForgeMind ADK 2 Workflow Runtime Implementation Plan", "id": "3c36566c-d850-8156-bbe4-ebd80f6041d9"},
]

# =============================================================================
# KNOWN SUBPAGES (Tier 2 — within Research Vault)
# =============================================================================

RESEARCH_VAULT_SUBPAGES = [
    {"title": "🧩 Research Entry Template", "id": "3bf6566c-d850-81df-a81f-dd93f38ec226"},
    {"title": "🔎 RV-001 — AI Coding Agents Increase the Need for Context-Aware PR Validation", "id": "3bf6566c-d850-813c-a98d-e1c87b58bd84"},
    {"title": "🔎 RV-002 — CI/CD Failure Diagnosis Is Evidence-Rich but Contextually Fragmented", "id": "3bf6566c-d850-8130-ab30-ed0d957210cc"},
    {"title": "🔎 RV-003 — Notification Triage Is a Prioritization Problem", "id": "3bf6566c-d850-811a-8286-d358df7746ca"},
    {"title": "🔎 RV-004 — Agent-Generated Documentation Creates a Drift and QA Problem", "id": "3bf6566c-d850-81a3-a61b-f96235b401a5"},
    {"title": "🔎 RV-005 — Multi-Agent Engineering Requires Shared State, Evaluation, and Explicit Coordination", "id": "3bf6566c-d850-81b5-b2a2-d734f7a27476"},
    {"title": "🔬 RV-006 — Competitive Gap Map: ForgeMind Must Not Be Positioned as Another AI Code Reviewer", "id": "3bf6566c-d850-81bb-88a4-dd25573ae447"},
    {"title": "🔬 RV-007 — Competitive Deep Dive: PR Intelligence Is Commodity Unless It Connects Beyond the Pull Request", "id": "3bf6566c-d850-81b6-9f03-d66dbfdb9f44"},
    {"title": "🔬 RV-008 — Competitive Deep Dive: Incident Intelligence Is Strongly Covered by Existing Platforms", "id": "3bf6566c-d850-81f9-b700-e9311b8ab3ed"},
    {"title": "🔬 RV-009 — Notification Triage Is Better as a Supporting Signal Than a Standalone MVP Agent", "id": "3bf6566c-d850-815e-b18c-eda819b32137"},
]

# =============================================================================
# BOUNDARY SET — All in-scope page IDs
# =============================================================================

def get_boundary_ids() -> Set[str]:
    """Return the set of all in-scope Notion page IDs."""
    ids = {FORGEMIND_ROOT_PAGE_ID}
    for child in TIER_1_CHILDREN:
        ids.add(child["id"])
    for subpage in RESEARCH_VAULT_SUBPAGES:
        ids.add(subpage["id"])
    return ids


def get_all_known_pages() -> List[dict]:
    """Return a flat list of all known in-scope pages with metadata."""
    pages = [{"title": FORGEMIND_ROOT_PAGE_TITLE, "id": FORGEMIND_ROOT_PAGE_ID, "tier": 0, "parent": None}]
    for child in TIER_1_CHILDREN:
        pages.append({"title": child["title"], "id": child["id"], "tier": 1, "parent": FORGEMIND_ROOT_PAGE_TITLE})
    for subpage in RESEARCH_VAULT_SUBPAGES:
        pages.append({"title": subpage["title"], "id": subpage["id"], "tier": 2, "parent": "Research Vault"})
    return pages


def is_in_scope(page_id: str) -> bool:
    """Check whether a Notion page ID is within the ForgeMind boundary."""
    return page_id in get_boundary_ids()


# =============================================================================
# ENFORCEMENT — Runtime boundary guards
# =============================================================================

class BoundaryViolationError(Exception):
    """Raised when an operation attempts to access a page outside the ForgeMind boundary."""
    pass


def enforce_boundary(page_id: str) -> None:
    """
    Verify a page ID is within scope before any API operation.
    
    Args:
        page_id: The Notion page ID to check.
    
    Raises:
        BoundaryViolationError: If the page is outside the ForgeMind tree.
    """
    if not is_in_scope(page_id):
        raise BoundaryViolationError(
            f"Page {page_id} is outside the ForgeMind boundary. "
            f"Operations are restricted to the ForgeMind tree rooted at "
            f"{FORGEMIND_ROOT_PAGE_ID}. "
            f"Add the page to the boundary definition first if it should be in scope."
        )


def filter_in_scope(page_ids: list) -> List[str]:
    """Filter a list of page IDs to only those within the boundary."""
    boundary = get_boundary_ids()
    return [pid for pid in page_ids if pid in boundary]


# =============================================================================
# BOUNDARY METADATA
# =============================================================================

BOUNDARY_METADATA = {
    "root_page_id": FORGEMIND_ROOT_PAGE_ID,
    "root_page_title": FORGEMIND_ROOT_PAGE_TITLE,
    "total_known_pages": len(get_all_known_pages()),
    "tier_1_children": len(TIER_1_CHILDREN),
    "tier_2_known": len(RESEARCH_VAULT_SUBPAGES),
    "last_verified": "2026-08-22",
    "description": "ForgeMind Notion Knowledge Base boundary — all descendants of the root page are in scope. Pages outside this tree are out of bounds.",
}


if __name__ == "__main__":
    print("=" * 80)
    print("ForgeMind Notion Boundary Definition")
    print("=" * 80)
    print(f"Root: {FORGEMIND_ROOT_PAGE_TITLE}")
    print(f"Root ID: {FORGEMIND_ROOT_PAGE_ID}")
    print(f"Total known pages: {len(get_all_known_pages())}")
    print(f"  - Tier 0 (Root): 1")
    print(f"  - Tier 1 (Direct children): {len(TIER_1_CHILDREN)}")
    print(f"  - Tier 2 (Known subpages): {len(RESEARCH_VAULT_SUBPAGES)}")
    print()
    print("Boundary enforcement: ENABLED")
    print(f"  is_in_scope('{FORGEMIND_ROOT_PAGE_ID}'): {is_in_scope(FORGEMIND_ROOT_PAGE_ID)}")
    print(f"  is_in_scope('external-page-id'): {is_in_scope('external-page-id')}")
    print()
    print("All in-scope pages:")
    for p in get_all_known_pages():
        print(f"  [Tier {p['tier']}] {p['title']} ({p['id']})")
    print("=" * 80)
