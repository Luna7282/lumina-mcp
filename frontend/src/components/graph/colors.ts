import type { GraphEdge, GraphNode } from "../../api/types";

export const NODE_COLORS: Record<GraphNode["type"], string> = {
  class: "#4f9cf9",
  function: "#67e8a4",
  method: "#67e8a4",
  route: "#f9a54f",
  model: "#c084fc",
  import: "#6b7280",
  module: "#f1f5f9",
};

export const EDGE_COLORS: Record<GraphEdge["confidence"], string> = {
  EXTRACTED: "#ffffff",
  INFERRED: "#ffffff",
  AMBIGUOUS: "#ffffff",
};

export const EDGE_OPACITY: Record<GraphEdge["confidence"], number> = {
  EXTRACTED: 0.4,
  INFERRED: 0.15,
  AMBIGUOUS: 0.05,
};

export function nodeColor(type: GraphNode["type"]): string {
  return NODE_COLORS[type] ?? "#f1f5f9";
}
