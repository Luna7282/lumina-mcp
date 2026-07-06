import networkx as nx

try:
    from graspologic.partition import leiden
    HAS_LEIDEN = True
except ImportError:
    HAS_LEIDEN = False


def _connected_components_fallback(G: nx.Graph) -> dict[str, int]:
    communities: dict[str, int] = {}
    for i, component in enumerate(nx.connected_components(G)):
        for node in component:
            communities[node] = i
    return communities


def detect_communities(G: nx.Graph) -> dict[str, int]:
    """
    Run Leiden community detection on the graph.
    Returns {node_id: community_id}.
    No embeddings needed — pure graph topology.
    """
    if len(G.nodes) < 2:
        return {n: 0 for n in G.nodes}

    if HAS_LEIDEN:
        try:
            partition = leiden(G)
            return {node: int(community) for node, community in partition.items()}
        except Exception:
            pass

    # Fallback: connected components as communities
    return _connected_components_fallback(G)


def get_community_summary(G: nx.Graph, communities: dict[str, int]) -> dict[int, dict]:
    """
    Summarize each community: top nodes, languages, file paths.
    """
    community_nodes: dict[int, list[str]] = {}
    for node_id, comm_id in communities.items():
        community_nodes.setdefault(comm_id, []).append(node_id)

    summaries = {}
    for comm_id, node_ids in community_nodes.items():
        degrees = {n: G.degree(n) for n in node_ids}
        top_nodes = sorted(degrees, key=degrees.get, reverse=True)[:5]
        files = list({G.nodes[n].get("source_file", "") for n in node_ids})
        summaries[comm_id] = {
            "size": len(node_ids),
            "top_nodes": [G.nodes[n].get("label", n) for n in top_nodes],
            "files": files[:10],
        }
    return summaries
