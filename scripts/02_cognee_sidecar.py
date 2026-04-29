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
# (e.g. macOS).
try:
    import sys
    import pysqlite3  # type: ignore
    sys.modules["sqlite3"] = pysqlite3
    sys.modules["sqlite3.dbapi2"] = pysqlite3.dbapi2
except ImportError:
    pass
# --- END sqlite3 shim --------------------------------------------------------

"""
Cognee sidecar: FastAPI service exposing /remember and /recall.

The OpenClaw Node.js plugin will call this over localhost HTTP.

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
os.environ.setdefault("EMBEDDING_PROVIDER", "openai")
os.environ.setdefault("EMBEDDING_MODEL", "openai/text-embedding-3-small")
os.environ.setdefault("EMBEDDING_DIMENSIONS", "1536")
os.environ.setdefault("GRAPH_DATASET_DATABASE_HANDLER", "falkor_graph_local")
os.environ.setdefault("VECTOR_DATASET_DATABASE_HANDLER", "falkor_vector_local")
os.environ.setdefault("GRAPH_DB_URL", "localhost")
os.environ.setdefault("GRAPH_DB_PORT", "6379")
os.environ.setdefault("ENABLE_BACKEND_ACCESS_CONTROL", "false")

import cognee
from cognee import SearchType, config
from cognee_community_hybrid_adapter_falkor import register  # noqa: F401


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


@asynccontextmanager
async def lifespan(_: FastAPI):
    _configure()
    yield


app = FastAPI(title="cognee-sidecar", lifespan=lifespan)
_lock = asyncio.Lock()


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
    async with _lock:
        try:
            await cognee.add(body.text)
            await cognee.cognify()
            return {"ok": True}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/recall")
async def recall(body: RecallIn) -> dict:
    try:
        results = await cognee.search(
            query_type=SearchType.GRAPH_COMPLETION,
            query_text=body.query,
        )
        return {"ok": True, "results": list(results)[: body.top_k]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/prune")
async def prune() -> dict:
    async with _lock:
        await cognee.prune.prune_data()
        await cognee.prune.prune_system(metadata=True)
        return {"ok": True}
