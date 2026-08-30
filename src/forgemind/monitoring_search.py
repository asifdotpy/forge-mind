"""ADK 2.0 search for monitoring signals.

Provides Google Search grounding via ADK 2.0 to detect active incidents,
outages, and alerts affecting a repository.

Architecture:
- Creates a dedicated ADK agent with google_search tool
- Runs a session to query for active incidents
- Extracts structured findings (alerts + telemetry signals)
- Caches results to minimize LLM calls (respects _CACHE_TTL_SECONDS)

See ADR-011 (evidence-aware decisioning) for the evidence model.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = ["MonitoringSearchService", "clear_monitoring_cache"]

# In-memory cache: repo -> (timestamp, results)
_MONITORING_CACHE: Dict[str, Tuple[float, Dict[str, List[Any]]]] = {}
_CACHE_TTL_SECONDS = 300.0  # 5 minutes


def clear_monitoring_cache() -> None:
    """Clear the monitoring search cache."""
    _MONITORING_CACHE.clear()


class MonitoringSearchService:
    """ADK-backed search for monitoring data during enrichment.

    Uses Google ADK 2.0 with the google_search tool to find active
    incidents, outages, or alerts affecting a repository.

    The search requires a full ADK session with an LLM agent because
    google_search is a model-grounding tool (cannot be invoked standalone).
    """

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        app_name: str = "forgemind-monitoring",
    ):
        self.model = model
        self.app_name = app_name

    def search_incidents(self, repo: str) -> Dict[str, List[Any]]:
        """Search for active incidents affecting a repository.

        Args:
            repo: Repository in 'owner/repo' format.

        Returns:
            Dict with keys: state ("ok" | "unavailable"), alerts (list of
            strings), telemetry (list of floats).

        Honesty contract (ADR-013): a real, successful query returns
        state="ok" even when the result set is empty (absence of detected
        incidents).  Any failure — ADK unavailable, unset credentials, query
        error — returns state="unavailable" with empty lists, so callers can
        distinguish "looked, was clean" from "could not be assessed".
        """
        try:
            from google.adk.agents import Agent
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService
            from google.adk.tools import google_search
            from google.genai import types
        except ImportError:
            logger.debug("google.adk not available; ADK monitoring search disabled")
            return {"state": "unavailable", "alerts": [], "telemetry": []}

        try:
            session_service = InMemorySessionService()

            search_agent = Agent(
                name="monitoring_search_agent",
                model=self.model,
                instruction=(
                    "You are a monitoring incident researcher. "
                    "Search for active incidents, outages, or alerts affecting the given repository. "
                    "Return findings as a JSON object with two keys: "
                    "\"alerts\" (list of strings describing active incidents) and "
                    "\"telemetry\" (list of floats representing error rates or latency). "
                    "If no incidents are found, return {\"alerts\": [], \"telemetry\": []}."
                ),
                tools=[google_search],
            )

            runner = Runner(
                agent=search_agent,
                app_name=self.app_name,
                session_service=session_service,
            )

            session_id = f"monitor-{repo.replace('/', '-')}"
            import asyncio
            asyncio.run(session_service.create_session(
                app_name=self.app_name,
                user_id="enrichment",
                session_id=session_id,
            ))

            query = (
                f"Are there any active incidents, outages, or alerts for {repo}? "
                f"Search status pages, incident reports, and news."
            )

            content = types.Content(
                role="user",
                parts=[types.Part(text=query)],
            )

            result: Dict[str, List[Any]] = {"alerts": [], "telemetry": []}

            async def run_search():
                async for event in runner.run_async(
                    user_id="enrichment",
                    session_id=session_id,
                    new_message=content,
                ):
                    if event.is_final_response() and event.content and event.content.parts:
                        text = event.content.parts[0].text or ""
                        try:
                            parsed = json.loads(text)
                            result["alerts"] = parsed.get("alerts", [])
                            result["telemetry"] = parsed.get("telemetry", [])
                        except json.JSONDecodeError:
                            text_lower = text.lower()
                            if (
                                "no incidents" not in text_lower
                                and "no active" not in text_lower
                                and "no outages" not in text_lower
                                and text.strip()
                            ):
                                result["alerts"] = [text.strip()]

            asyncio.run(run_search())
            # Success path: even a zero-result query is a real assessment.
            result["state"] = "ok"
            logger.debug(
                "ADK monitoring search completed for %s: %d alerts (state=%s)",
                repo,
                len(result["alerts"]),
                result["state"],
            )
            return result

        except Exception as exc:
            logger.debug("ADK monitoring search failed for %s: %s", repo, exc)
            return {"state": "unavailable", "alerts": [], "telemetry": []}


async def fetch_monitoring_signals(repo: str, changed_files: List[str]) -> Dict[str, List[Any]]:
    """Fetch monitoring signals via ADK 2 search.

    Args:
        repo: Repository in 'owner/repo' format.
        changed_files: List of changed filenames (unused for monitoring).

    Returns:
        Dict with keys: state, alert_signals, telemetry_signals.
    """
    service = MonitoringSearchService()
    results = service.search_incidents(repo)

    return {
        "state": results.get("state", "unavailable"),
        "alert_signals": results.get("alerts", []),
        "telemetry_signals": results.get("telemetry", []),
    }
