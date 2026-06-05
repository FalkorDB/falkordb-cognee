# --- BEGIN sqlite3 shim ------------------------------------------------------
# Cognee 1.x uses a SELECT pattern that segfaults inside the system
# libsqlite3 shipped on Ubuntu 24.04 (3.45.1) and other older distros:
#
#   __strlen_evex -> sqlite3DbStrDup -> sqlite3Select -> sqlite3_prepare_v2
#   -> _sqlite3.cpython-312 -> sqlalchemy -> cognee
#
# Work around it by forcing pysqlite3-binary (bundles SQLite >= 3.51) in
# place of the stdlib sqlite3 module. Must run BEFORE cognee/sqlalchemy
# are imported. Harmless on platforms that already have a recent SQLite
# (e.g. macOS, or the cognee/cognee Docker image).
try:
    import sys
    import pysqlite3  # type: ignore
    sys.modules["sqlite3"] = pysqlite3
    sys.modules["sqlite3.dbapi2"] = pysqlite3.dbapi2
except ImportError:
    pass
# --- END sqlite3 shim --------------------------------------------------------

"""
Cognee sidecar: FastAPI service exposing /remember, /recall and /prune.

The OpenClaw Node.js plugin calls this over localhost HTTP.

Multi-user / multi-graph
------------------------
With ``ENABLE_BACKEND_ACCESS_CONTROL=true`` (the default here) Cognee gives
every user their own isolated FalkorDB graph + vector store. The caller's
``user_id`` is deterministically mapped to a Cognee User (created on first
use), e.g. the OpenClaw agent-scoped id ``guy:agent:elizabeth`` becomes the
email ``guy_agent_elizabeth@example.com``. The friendly-naming handlers in
``cognee_falkor_naming`` then give that user a readable graph name
(``guy__elizabeth``) instead of the dataset UUID. Set
``ENABLE_BACKEND_ACCESS_CONTROL=false`` for legacy single-graph mode.

Run with:
    source ~/.cognee-venv/bin/activate
    uvicorn 02_cognee_sidecar:app --host 127.0.0.1 --port 8765
"""
import asyncio
import os
import pathlib
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

load_dotenv(os.path.expanduser("~/.openclaw/.env"))

# Cognee reads LLM_API_KEY (not OPENAI_API_KEY) — map it across.
if os.getenv("OPENAI_API_KEY") and not os.getenv("LLM_API_KEY"):
    os.environ["LLM_API_KEY"] = os.environ["OPENAI_API_KEY"]
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("LLM_MODEL", "openai/gpt-4o-mini")
# Cognee 1.1.0 added a SECOND model knob — the BAML-instructed
# extraction pipeline used by cognify — and defaults BOTH knobs to
# "gpt-5-mini" / "openai/gpt-5-mini", which require OpenAI org
# verification. Pin BAML_LLM_MODEL to gpt-4o-mini too, otherwise
# cognify retries forever with a NotFoundError.
os.environ.setdefault("BAML_LLM_PROVIDER", "openai")
os.environ.setdefault("BAML_LLM_MODEL", "gpt-4o-mini")
if os.getenv("LLM_API_KEY") and not os.getenv("BAML_LLM_API_KEY"):
    os.environ["BAML_LLM_API_KEY"] = os.environ["LLM_API_KEY"]
os.environ.setdefault("EMBEDDING_PROVIDER", "openai")
os.environ.setdefault("EMBEDDING_MODEL", "openai/text-embedding-3-small")
os.environ.setdefault("EMBEDDING_DIMENSIONS", "1536")
os.environ.setdefault("GRAPH_DB_URL", "localhost")
os.environ.setdefault("GRAPH_DB_PORT", "6379")

# Per-user isolated graphs (multiple named FalkorDB graphs). Set to "false"
# for legacy single-graph mode. See docs/SETUP.md.
os.environ.setdefault("ENABLE_BACKEND_ACCESS_CONTROL", "true")

# Friendly, human-readable FalkorDB graph names instead of dataset UUIDs.
# Selects the cognee_falkor_naming handlers registered below. The naming
# rule itself is configured via COGNEE_GRAPH_NAME_* env vars (see that
# module's docstring). Set COGNEE_FRIENDLY_GRAPH_NAMES=false to keep the
# adapter's native UUID names.
_FRIENDLY_NAMES = os.getenv("COGNEE_FRIENDLY_GRAPH_NAMES", "true").lower() == "true"
if _FRIENDLY_NAMES:
    os.environ.setdefault("GRAPH_DATASET_DATABASE_HANDLER", "falkor_graph_local_named")
    os.environ.setdefault("VECTOR_DATASET_DATABASE_HANDLER", "falkor_vector_local_named")
else:
    os.environ.setdefault("GRAPH_DATASET_DATABASE_HANDLER", "falkor_graph_local")
    os.environ.setdefault("VECTOR_DATASET_DATABASE_HANDLER", "falkor_vector_local")

# Cognee 1.1.0 added a startup LLM connectivity test that can hang on
# slow/cold networks (notably inside Docker). The cap-on-resources
# tunables below bound the new dataset LRU + cognify queue added in 1.1.0.
os.environ.setdefault("COGNEE_SKIP_CONNECTION_TEST", "false")
os.environ.setdefault("DATABASE_MAX_LRU_CACHE_SIZE", "4")
os.environ.setdefault("DATASET_QUEUE_MAX_CONCURRENT", "2")

import cognee
from cognee import SearchType, config
from cognee_community_hybrid_adapter_falkor import register  # noqa: F401
from cognee.infrastructure.databases.relational import create_db_and_tables
from cognee.modules.users.methods import create_user, get_user_by_email

# Register the friendly graph-name handlers unconditionally (they are only
# *selected* when COGNEE_FRIENDLY_GRAPH_NAMES is on, but registering them
# always means rows that stored a *_named handler still resolve).
from cognee_falkor_naming import register_named_handlers

register_named_handlers()

# Make recall resilient: a single legacy/malformed node or edge (missing
# id / source_node_id / target_node_id) would otherwise crash the adapter's
# whole-graph read and make recall return "no information" for the entire
# graph. Skip such records instead. Disable with COGNEE_RESILIENT_GRAPH_READ=false.
if os.getenv("COGNEE_RESILIENT_GRAPH_READ", "true").lower() == "true":
    from cognee_falkor_resilience import install_resilient_graph_read

    install_resilient_graph_read()


def _configure() -> None:
    base = pathlib.Path.home() / ".cognee"
    config.system_root_directory(str(base / "system"))
    config.data_root_directory(str(base / "data"))
    config.set_relational_db_config({"db_provider": "sqlite"})
    config.set_vector_db_config({
        "vector_db_provider": "falkor",
        "vector_db_url": os.getenv("FALKOR_HOST", "localhost"),
        "vector_db_port": int(os.getenv("FALKOR_PORT", "6379")),
    })
    config.set_graph_db_config({
        "graph_database_provider": "falkor",
        "graph_database_url": os.getenv("FALKOR_HOST", "localhost"),
        "graph_database_port": int(os.getenv("FALKOR_PORT", "6379")),
    })


# --- per-user mapping --------------------------------------------------------
_user_cache: dict[str, object] = {}
_user_cache_lock = asyncio.Lock()
_lock = asyncio.Lock()


def _email_for(user_id: str | None) -> str:
    """Deterministic, valid email derived from the caller's user_id.

    Cognee/pydantic-email requires a real-looking TLD, so we use @example.com.
    Non-alphanumeric characters (e.g. the ``:`` in OpenClaw's
    ``guy:agent:elizabeth``) collapse to ``_``.
    """
    raw = (user_id or "default").strip() or "default"
    safe = "".join(ch if ch.isalnum() else "_" for ch in raw).strip("_").lower()
    safe = safe or "default"
    return f"{safe}@example.com"


async def _ensure_user(user_id: str | None):
    email = _email_for(user_id)
    if email in _user_cache:
        return _user_cache[email]
    async with _user_cache_lock:
        if email in _user_cache:
            return _user_cache[email]
        try:
            u = await create_user(email=email, password="x")
        except Exception:
            u = await get_user_by_email(email)
        _user_cache[email] = u
        return u


@asynccontextmanager
async def lifespan(_: FastAPI):
    _configure()
    await create_db_and_tables()
    yield


app = FastAPI(title="cognee-sidecar", lifespan=lifespan)


class RememberIn(BaseModel):
    text: str
    user_id: str | None = None
    agent_id: str | None = None


class RecallIn(BaseModel):
    query: str
    user_id: str | None = None
    agent_id: str | None = None
    top_k: int = 5


@app.get("/healthz")
async def health() -> dict:
    return {"ok": True}


@app.post("/remember")
async def remember(body: RememberIn) -> dict:
    user = await _ensure_user(body.user_id)
    async with _lock:
        try:
            await cognee.add(body.text, user=user)
            await cognee.cognify(user=user)
            return {"ok": True, "user": user.email}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/recall")
async def recall(body: RecallIn) -> dict:
    user = await _ensure_user(body.user_id)
    try:
        results = await cognee.search(
            query_type=SearchType.GRAPH_COMPLETION,
            query_text=body.query,
            user=user,
        )
        # Cognee 1.0.x returned list[str] directly. Cognee 1.1.0 wraps
        # each hit in {dataset_id, dataset_name, dataset_tenant_id,
        # search_result: [str, ...]}. Flatten back to list[str] so the
        # documented `{ok, results: string[]}` contract holds across
        # both versions.
        flat: list[str] = []
        for r in results or []:
            if isinstance(r, str):
                flat.append(r)
            elif isinstance(r, dict) and isinstance(r.get("search_result"), list):
                for s in r["search_result"]:
                    flat.append(s if isinstance(s, str) else str(s))
            else:
                flat.append(str(r))
        return {"ok": True, "user": user.email, "results": flat[: body.top_k]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/prune")
async def prune() -> dict:
    async with _lock:
        try:
            await cognee.prune.prune_data()
            await cognee.prune.prune_system(metadata=True)
            await create_db_and_tables()
            _user_cache.clear()
            return {"ok": True}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
