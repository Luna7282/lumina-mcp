import type { GraphNode } from "../../api/types";

export type Vec3 = [number, number, number];

export function computeLayout(
  nodes: GraphNode[],
  communities: Record<string, number>,
): Record<string, Vec3> {
  const communityIds = [...new Set(Object.values(communities))];
  const communityCount = Math.max(communityIds.length, 1);

  // Community centers spread evenly on a sphere (golden-angle spiral).
  const commCenters: Record<number, Vec3> = {};
  communityIds.forEach((cid, i) => {
    const phi = Math.acos(1 - (2 * (i + 0.5)) / communityCount);
    const theta = Math.PI * (1 + Math.sqrt(5)) * i;
    commCenters[cid] = [
      8 * Math.sin(phi) * Math.cos(theta),
      8 * Math.sin(phi) * Math.sin(theta),
      8 * Math.cos(phi),
    ];
  });

  const positions: Record<string, Vec3> = {};
  nodes.forEach((node) => {
    const cid = communities[node.id] ?? 0;
    const center = commCenters[cid] ?? [0, 0, 0];
    const spread = 2.5;
    positions[node.id] = [
      center[0] + (Math.random() - 0.5) * spread,
      center[1] + (Math.random() - 0.5) * spread,
      center[2] + (Math.random() - 0.5) * spread,
    ];
  });

  return positions;
}

export function computeDegrees(
  nodes: GraphNode[],
  edges: { source: string; target: string }[],
): Record<string, number> {
  const degrees: Record<string, number> = {};
  nodes.forEach((n) => (degrees[n.id] = 0));
  edges.forEach((e) => {
    degrees[e.source] = (degrees[e.source] ?? 0) + 1;
    degrees[e.target] = (degrees[e.target] ?? 0) + 1;
  });
  return degrees;
}
