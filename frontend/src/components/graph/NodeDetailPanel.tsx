import type { GraphEdge, GraphNode } from "../../api/types";
import { nodeColor } from "./colors";

interface NodeDetailPanelProps {
  node: GraphNode;
  edges: GraphEdge[];
  communityId: number | undefined;
  onClose: () => void;
  onSelectNode: (nodeId: string) => void;
  onShowCommunity: (communityId: number) => void;
  onExplain: () => void;
}

const RELATION_COLORS: Record<GraphEdge["relation"], string> = {
  calls: "text-blue-400",
  imports: "text-green-400",
  inherits: "text-purple-400",
  handles: "text-orange-400",
  contains: "text-gray-400",
  implements: "text-cyan-400",
};

export default function NodeDetailPanel({
  node,
  edges,
  communityId,
  onClose,
  onSelectNode,
  onShowCommunity,
  onExplain,
}: NodeDetailPanelProps) {
  const visibleEdges = edges.slice(0, 6);
  const remaining = edges.length - visibleEdges.length;

  return (
    <div className="absolute bottom-4 left-4 right-4 z-10 rounded-xl border border-purple-500/30 bg-gray-900/95 p-4 shadow-2xl shadow-purple-900/20 backdrop-blur md:right-auto md:w-80">
      {/* Header */}
      <div className="mb-3 flex items-start justify-between">
        <div className="min-w-0">
          <div className="mb-1 flex items-center gap-2">
            <div className="h-2 w-2 rounded-full" style={{ backgroundColor: nodeColor(node.type) }} />
            <span className="text-xs uppercase tracking-wider text-gray-400">{node.type}</span>
          </div>
          <h3 className="truncate text-sm font-semibold text-white">{node.label}</h3>
          <p className="mt-0.5 truncate text-xs text-gray-500">
            {node.source_file}
            {node.source_location ? `:${node.source_location}` : ""}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="shrink-0 p-1 text-xs text-gray-600 hover:text-white"
        >
          ✕
        </button>
      </div>

      {/* Docstring */}
      {node.docstring && (
        <p className="mb-3 border-l-2 border-purple-500/50 pl-2 text-xs text-gray-300">
          {node.docstring}
        </p>
      )}

      {/* Connections */}
      <div className="space-y-1">
        <p className="mb-1 text-xs uppercase tracking-wider text-gray-500">Connections</p>
        {visibleEdges.length === 0 && <p className="text-xs text-gray-600">No connections found</p>}
        {visibleEdges.map((edge, i) => {
          const otherId = edge.source === node.id ? edge.target : edge.source;
          return (
            <div
              key={`${edge.source}-${edge.target}-${edge.relation}-${i}`}
              onClick={() => onSelectNode(otherId)}
              className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-xs hover:bg-white/5"
            >
              <span className="text-gray-500">{edge.source === node.id ? "→" : "←"}</span>
              <span className={`rounded px-1 text-xs ${RELATION_COLORS[edge.relation]}`}>
                {edge.relation}
              </span>
              <span className="truncate text-gray-300">{otherId.split("::").pop()}</span>
              <span className="ml-auto shrink-0 text-xs text-gray-600">
                {edge.confidence === "EXTRACTED" ? "✓" : "~"}
              </span>
            </div>
          );
        })}
        {remaining > 0 && <p className="pl-1 text-xs text-gray-600">+{remaining} more</p>}
      </div>

      {/* Actions */}
      <div className="mt-3 flex gap-2 border-t border-gray-800 pt-3">
        {communityId !== undefined && (
          <button
            type="button"
            onClick={() => onShowCommunity(communityId)}
            className="rounded bg-purple-900/20 px-2 py-1 text-xs text-purple-400 hover:text-purple-300"
          >
            Show community
          </button>
        )}
        <button
          type="button"
          onClick={onExplain}
          className="rounded bg-blue-900/20 px-2 py-1 text-xs text-blue-400 hover:text-blue-300"
        >
          Explain this →
        </button>
      </div>
    </div>
  );
}
