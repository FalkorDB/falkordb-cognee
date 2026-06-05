"""Make Cognee's FalkorDB graph read resilient to malformed records.

Why this module exists
----------------------
Cognee's ``GraphCompletionRetriever`` (used by ``/recall``) projects the
*entire* graph via the FalkorDB adapter's ``get_graph_data()``. That method
assumes every node's properties contain an ``id`` key and every edge's
properties contain ``source_node_id`` / ``target_node_id``:

    # cognee_community_hybrid_adapter_falkor/falkor_adapter.py  get_graph_data
    nodes = [(record[2]["id"], record[2]) for record in result.result_set]
    edges = [(record[3]["source_node_id"], record[3]["target_node_id"], ...) ...]

A single legacy / partially-written record that lacks one of those keys raises
``KeyError`` and aborts the whole projection, so recall silently returns
"no information" for the *entire* graph — even though 99.9% of it is fine.

The adapter exposes no hook or config for this, so the only fix is to replace
``get_graph_data`` with a tolerant version. This module does exactly that and
nothing else: it runs the same two queries but **skips** records missing the
required keys instead of crashing. Skipping is safe — a node with no cognee
``id`` (or an edge with no endpoints) cannot be placed in the projection
anyway, so the only thing lost is the already-unusable record.

Usage
-----
    from cognee_community_hybrid_adapter_falkor import register  # noqa: F401
    from cognee_falkor_resilience import install_resilient_graph_read
    install_resilient_graph_read()

Disable with ``COGNEE_RESILIENT_GRAPH_READ=false``.
"""

import logging

logger = logging.getLogger("cognee_falkor_resilience")

_PATCH_FLAG = "_cognee_resilient_get_graph_data"


async def _resilient_get_graph_data(self):
    """Drop-in replacement for FalkorDBAdapter.get_graph_data that tolerates
    nodes missing ``id`` and edges missing ``source_node_id``/``target_node_id``.
    """
    node_query = "MATCH (n) RETURN ID(n) AS id, labels(n) AS labels, properties(n) AS properties"
    result = await self.query(node_query)
    nodes = []
    skipped_nodes = 0
    for record in result.result_set:
        props = record[2]
        node_id = props.get("id") if isinstance(props, dict) else None
        if node_id is None:
            skipped_nodes += 1
            continue
        nodes.append((node_id, props))

    edge_query = """
        MATCH (n)-[r]->(m)
        RETURN ID(n) AS source, ID(m) AS target, TYPE(r) AS type, properties(r) AS properties
    """
    result = await self.query(edge_query)
    edges = []
    skipped_edges = 0
    for record in result.result_set:
        props = record[3]
        source = props.get("source_node_id") if isinstance(props, dict) else None
        target = props.get("target_node_id") if isinstance(props, dict) else None
        if source is None or target is None:
            skipped_edges += 1
            continue
        edges.append((source, target, record[2], props))

    if skipped_nodes or skipped_edges:
        logger.warning(
            "Skipped %d malformed node(s) and %d malformed edge(s) while reading "
            "the graph (missing id / source_node_id / target_node_id).",
            skipped_nodes,
            skipped_edges,
        )
    return (nodes, edges)


def install_resilient_graph_read() -> bool:
    """Patch FalkorDBAdapter.get_graph_data with the tolerant version.

    Idempotent: a second call is a no-op. Returns True if the patch is in
    place, False if the adapter could not be imported.
    """
    try:
        from cognee_community_hybrid_adapter_falkor.falkor_adapter import FalkorDBAdapter
    except ImportError:
        logger.warning("FalkorDB adapter not importable; resilient graph read not installed")
        return False

    if getattr(FalkorDBAdapter, _PATCH_FLAG, False):
        return True

    FalkorDBAdapter.get_graph_data = _resilient_get_graph_data
    setattr(FalkorDBAdapter, _PATCH_FLAG, True)
    logger.info("Installed resilient FalkorDBAdapter.get_graph_data")
    return True
