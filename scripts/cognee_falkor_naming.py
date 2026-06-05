"""Config-driven, human-readable FalkorDB graph/vector names for Cognee.

Why this module exists
----------------------
When Cognee runs in multi-user / backend-access-control mode
(``ENABLE_BACKEND_ACCESS_CONTROL=true``) every ``(user, dataset)`` pair is
backed by its own FalkorDB graph + vector store. The community adapter
``cognee_community_hybrid_adapter_falkor`` names each of those after the
dataset's UUID:

    # FalkorDatasetDatabaseHandlerGraphLocal.create_dataset
    graph_db_name = f"{dataset_id}"      # e.g. "4aaeaca4a8255cdca3b9e6cb..."

That is unreadable in the FalkorDB browser and in ``redis-cli GRAPH.LIST``.
The adapter exposes **no** configuration hook for the name, so historically
this repo monkey-patched the adapter's private ``create_dataset``.

This module replaces that monkey-patch with thin subclasses registered
through the adapter's *public* extension API
(``use_dataset_database_handler``). Selecting them is a normal env-var
switch, and the naming rule itself is fully configurable.

How to use
----------
Call :func:`register_named_handlers` once, after importing
``cognee_community_hybrid_adapter_falkor.register``, then point Cognee at the
registered handler names::

    from cognee_community_hybrid_adapter_falkor import register  # noqa: F401
    from cognee_falkor_naming import register_named_handlers
    g, v = register_named_handlers()
    os.environ["GRAPH_DATASET_DATABASE_HANDLER"] = g   # "falkor_graph_local_named"
    os.environ["VECTOR_DATASET_DATABASE_HANDLER"] = v  # "falkor_vector_local_named"

Configuration (environment variables)
-------------------------------------
``COGNEE_GRAPH_NAME_OVERRIDES``
    JSON object giving each user an explicit graph name. Checked first, so
    it always wins. Keys may be the full email or just the local-part::

        COGNEE_GRAPH_NAME_OVERRIDES='{"will_agent_elizabeth": "elizabeth"}'

    This is the easiest and most durable way to name a graph, and is the
    recommended way to pin a name that was renamed out-of-band.

``COGNEE_GRAPH_NAME_FROM``
    Naming strategy when no override matches. One of:
      - ``email-localpart`` (default) — derive from the user's email
        local-part, rewriting ``_agent_`` to ``COGNEE_AGENT_SEPARATOR``
        (``will@..`` -> ``will``; ``will_agent_elizabeth@..`` -> ``will__elizabeth``).
      - ``dataset-id`` — keep the adapter's native UUID name.
      - ``static`` — force every dataset to ``COGNEE_GRAPH_NAME_STATIC``
        (all datasets then SHARE one graph; a warning is logged).

``COGNEE_AGENT_SEPARATOR``
    Separator that replaces ``_agent_`` in the email-localpart strategy.
    Default ``__``.

``COGNEE_GRAPH_NAME_STATIC``
    The single graph name used when ``COGNEE_GRAPH_NAME_FROM=static``.

All generated names are sanitised to ``[A-Za-z0-9_]`` (other characters
become ``_``) and capped at 200 chars so they are always valid FalkorDB
keys. If a rule yields an empty name the adapter's UUID name is used as a
safe fallback.

Note on collisions: distinct ``(user, dataset)`` pairs that resolve to the
same name share one FalkorDB graph. The default per-user strategy assumes
one logical dataset per user (as in the OpenClaw memory setup). Use the
override map or ``dataset-id`` if you need stronger guarantees.
"""

import json
import logging
import os
from typing import Optional
from uuid import UUID

from cognee.infrastructure.databases.dataset_database_handler import (
    use_dataset_database_handler,
)
from cognee_community_hybrid_adapter_falkor.FalkorDatasetDatabaseHandlerGraphLocal import (
    FalkorDatasetDatabaseHandlerGraphLocal,
)
from cognee_community_hybrid_adapter_falkor.FalkorDatasetDatabaseHandlerVectorLocal import (
    FalkorDatasetDatabaseHandlerVectorLocal,
)

logger = logging.getLogger("cognee_falkor_naming")

GRAPH_HANDLER_NAME = "falkor_graph_local_named"
VECTOR_HANDLER_NAME = "falkor_vector_local_named"

_MAX_NAME_LEN = 200


def _sanitize(name: str) -> str:
    """Reduce an arbitrary string to a safe FalkorDB key: [A-Za-z0-9_], capped."""
    safe = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in name)
    return safe.strip("_")[:_MAX_NAME_LEN]


def _overrides() -> dict:
    raw = os.getenv("COGNEE_GRAPH_NAME_OVERRIDES", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items()}
        logger.warning("COGNEE_GRAPH_NAME_OVERRIDES is not a JSON object; ignoring")
    except json.JSONDecodeError as exc:
        logger.warning("COGNEE_GRAPH_NAME_OVERRIDES is not valid JSON (%s); ignoring", exc)
    return {}


def friendly_name(user, dataset_id) -> str:
    """Resolve the FalkorDB graph/vector name for a (user, dataset).

    Falls back to the adapter's native ``str(dataset_id)`` whenever a rule
    cannot produce a usable name.
    """
    fallback = f"{dataset_id}"
    email = (getattr(user, "email", None) or "").strip()
    local = email.split("@", 1)[0] if email else ""

    # 1. Explicit overrides win (easiest, most durable).
    overrides = _overrides()
    for key in (local, email):
        if key and key in overrides:
            return _sanitize(overrides[key]) or fallback

    source = os.getenv("COGNEE_GRAPH_NAME_FROM", "email-localpart").lower()

    if source == "dataset-id":
        return fallback

    if source == "static":
        name = _sanitize(os.getenv("COGNEE_GRAPH_NAME_STATIC", ""))
        if name:
            logger.warning(
                "COGNEE_GRAPH_NAME_FROM=static: every dataset shares graph %r", name
            )
            return name
        return fallback

    # Default: derive from the email local-part.
    if not local:
        return fallback
    separator = os.getenv("COGNEE_AGENT_SEPARATOR", "__")
    return _sanitize(local.replace("_agent_", separator, 1)) or fallback


class FalkorGraphHandlerNamed(FalkorDatasetDatabaseHandlerGraphLocal):
    """Graph handler that swaps the UUID graph name for a friendly one."""

    @classmethod
    async def create_dataset(cls, dataset_id: Optional[UUID], user) -> dict:
        info = await super().create_dataset(dataset_id, user)
        info["graph_database_name"] = friendly_name(user, dataset_id)
        return info


class FalkorVectorHandlerNamed(FalkorDatasetDatabaseHandlerVectorLocal):
    """Vector handler that swaps the UUID vector-store name for a friendly one."""

    @classmethod
    async def create_dataset(cls, dataset_id: Optional[UUID], user) -> dict:
        info = await super().create_dataset(dataset_id, user)
        info["vector_database_name"] = friendly_name(user, dataset_id)
        return info


def register_named_handlers() -> tuple[str, str]:
    """Register the friendly-name handlers and return their handler names.

    Idempotent and side-effect-free beyond the registry insert, so it is safe
    to call unconditionally even when friendly naming is disabled (the
    handlers are simply not selected).
    """
    use_dataset_database_handler(GRAPH_HANDLER_NAME, FalkorGraphHandlerNamed, "falkor")
    use_dataset_database_handler(VECTOR_HANDLER_NAME, FalkorVectorHandlerNamed, "falkor")
    return GRAPH_HANDLER_NAME, VECTOR_HANDLER_NAME
