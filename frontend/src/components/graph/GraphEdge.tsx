import { useMemo } from "react";
import * as THREE from "three";
import type { GraphEdge as GraphEdgeType } from "../../api/types";
import { EDGE_OPACITY } from "./colors";
import type { Vec3 } from "./layout";

interface GraphEdgeProps {
  edges: GraphEdgeType[];
  positions: Record<string, Vec3>;
  highlightedNodeIds: Set<string> | null;
}

const CONFIDENCE_LEVELS: GraphEdgeType["confidence"][] = [
  "EXTRACTED",
  "INFERRED",
  "AMBIGUOUS",
];

function buildGeometry(
  edges: GraphEdgeType[],
  positions: Record<string, Vec3>,
): THREE.BufferGeometry {
  const vertices: number[] = [];
  edges.forEach((edge) => {
    const src = positions[edge.source];
    const tgt = positions[edge.target];
    if (!src || !tgt) return;
    vertices.push(...src, ...tgt);
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    "position",
    new THREE.BufferAttribute(new Float32Array(vertices), 3),
  );
  return geometry;
}

export default function GraphEdge({
  edges,
  positions,
  highlightedNodeIds,
}: GraphEdgeProps) {
  const grouped = useMemo(() => {
    const highlighted = edges.filter(
      (e) =>
        !highlightedNodeIds ||
        (highlightedNodeIds.has(e.source) && highlightedNodeIds.has(e.target)),
    );
    const dimmed = highlightedNodeIds
      ? edges.filter((e) => !highlighted.includes(e))
      : [];

    return CONFIDENCE_LEVELS.map((confidence) => ({
      confidence,
      highlightedGeometry: buildGeometry(
        highlighted.filter((e) => e.confidence === confidence),
        positions,
      ),
      dimmedGeometry: buildGeometry(
        dimmed.filter((e) => e.confidence === confidence),
        positions,
      ),
    }));
  }, [edges, positions, highlightedNodeIds]);

  return (
    <>
      {grouped.map(({ confidence, highlightedGeometry, dimmedGeometry }) => (
        <group key={confidence}>
          <lineSegments geometry={highlightedGeometry}>
            <lineBasicMaterial
              color="#ffffff"
              transparent
              opacity={EDGE_OPACITY[confidence]}
            />
          </lineSegments>
          {highlightedNodeIds && (
            <lineSegments geometry={dimmedGeometry}>
              <lineBasicMaterial
                color="#ffffff"
                transparent
                opacity={EDGE_OPACITY[confidence] * 0.1}
              />
            </lineSegments>
          )}
        </group>
      ))}
    </>
  );
}
