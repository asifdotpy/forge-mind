"""ForgeMind LLM adapter package (M3-B / ADR-010).

Thin, fail-closed bridge to Gemini 3.5 (via Vertex AI) used ONLY to fill
free-text ``observations`` / ``claims`` on the code-intelligence worker.
It never touches schema fields, provenance, confidence, or any other tier
output.  The heavy ``google-genai`` client is imported LAZILY inside the
adapter functions so ``import forgemind.llm`` (and therefore
``import forgemind``) works on a machine where the package is absent —
the 133-test offline suite must stay green without the dependency.

See ``adapter.py`` for the full contract and the fail-closed guarantee.
"""

from forgemind.llm.adapter import generate_claims, generate_observations

__all__ = ["generate_observations", "generate_claims"]
