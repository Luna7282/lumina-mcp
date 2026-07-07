import networkx as nx

from lumina_app.extract.schema import ExtractionResult


def build_graph(extractions: dict[str, ExtractionResult]) -> nx.Graph:
    """
    Merge all ExtractionResults into a single NetworkX graph.
    Resolve cross-file edges where possible.
    """
    G = nx.Graph()

    # Add all nodes
    for filepath, result in extractions.items():
        for node in result.nodes:
            G.add_node(
                node.id,
                **{
                    "label": node.label,
                    "type": node.type,
                    "source_file": node.source_file,
                    "source_location": node.source_location,
                    "docstring": node.docstring,
                    "language": result.language,
                },
            )

    # Build label → node_id index for cross-file resolution
    label_index: dict[str, list[str]] = {}
    for node_id, data in G.nodes(data=True):
        label = data["label"]
        label_index.setdefault(label, []).append(node_id)

    # Add all edges, resolving INFERRED cross-file calls.
    #
    # G is an *undirected* nx.Graph (required by the Leiden clustering step),
    # but our relations (inherits, calls, handles, imports, ...) are
    # inherently directional. NetworkX stores one shared data dict per pair
    # and G.edges(data=True) can hand it back as (u, v) OR (v, u) depending
    # on internal iteration order — so relying on the yielded tuple order
    # silently flips direction for some edges. Stash the true direction in
    # the data dict itself (under "source"/"target") so it survives
    # regardless of which order NetworkX later reports the pair in.
    for filepath, result in extractions.items():
        for edge in result.edges:
            # Resolve target if it's a label reference
            source = edge.source
            target = edge.target

            if source in G and target in G:
                G.add_edge(
                    source, target,
                    source=source, target=target,
                    relation=edge.relation, confidence=edge.confidence,
                )
            elif target not in G:
                # Try to resolve by label
                candidates = label_index.get(target, [])
                if len(candidates) == 1:
                    resolved_target = candidates[0]
                    G.add_edge(
                        source, resolved_target,
                        source=source, target=resolved_target,
                        relation=edge.relation, confidence="INFERRED",
                    )
                # else: dangling edge, skip (log warning)

    # Self-loops are never meaningful here — e.g. an import node's own label
    # matching its bare imported name resolves back to itself via the label
    # index above. Strip them rather than filtering per-extractor.
    G.remove_edges_from(nx.selfloop_edges(G))

    return G


def get_language_summary(extractions: dict[str, ExtractionResult]) -> dict[str, int]:
    """Count files per language."""
    summary: dict[str, int] = {}
    for result in extractions.values():
        lang = result.language
        summary[lang] = summary.get(lang, 0) + 1
    return summary


def get_god_nodes(G: nx.Graph, top_n: int = 10) -> list[dict]:
    """
    Find highest-degree nodes — architectural hubs.
    Same concept as Graphify's god_nodes analysis.
    """
    degree = dict(G.degree())
    sorted_nodes = sorted(degree.items(), key=lambda x: x[1], reverse=True)
    return [
        {
            "id": node_id,
            "label": G.nodes[node_id].get("label", node_id),
            "degree": deg,
            "type": G.nodes[node_id].get("type", "unknown"),
            "source_file": G.nodes[node_id].get("source_file", ""),
        }
        for node_id, deg in sorted_nodes[:top_n]
        if node_id in G.nodes
    ]
