import { useState } from "react";
import { Html } from "@react-three/drei";
import type { GraphNode as GraphNodeType } from "../../api/types";
import { nodeColor } from "./colors";
import type { Vec3 } from "./layout";

interface GraphNodeProps {
  node: GraphNodeType;
  position: Vec3;
  isGodNode: boolean;
  dimmed: boolean;
  isSelected: boolean;
  onHover: (node: GraphNodeType | null) => void;
  onClick: (node: GraphNodeType) => void;
  onDoubleClick: (node: GraphNodeType) => void;
}

export default function GraphNode({
  node,
  position,
  isGodNode,
  dimmed,
  isSelected,
  onHover,
  onClick,
  onDoubleClick,
}: GraphNodeProps) {
  const [hovered, setHovered] = useState(false);
  const color = nodeColor(node.type);
  const radius = isGodNode ? 0.4 : 0.15;
  const opacity = dimmed ? 0.1 : 1;

  return (
    <group position={position}>
      <mesh
        onPointerOver={(e) => {
          e.stopPropagation();
          setHovered(true);
          onHover(node);
          document.body.style.cursor = "pointer";
        }}
        onPointerOut={(e) => {
          e.stopPropagation();
          setHovered(false);
          onHover(null);
          document.body.style.cursor = "auto";
        }}
        onClick={(e) => {
          e.stopPropagation();
          onClick(node);
        }}
        onDoubleClick={(e) => {
          e.stopPropagation();
          onDoubleClick(node);
        }}
        scale={hovered || isSelected ? 1.25 : 1}
      >
        <sphereGeometry args={[radius, 16, 16]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={isGodNode ? 0.5 : 0.1}
          transparent
          opacity={opacity}
        />
      </mesh>

      {isGodNode && !dimmed && (
        <pointLight color={color} intensity={4} distance={3} decay={2} />
      )}

      {hovered && (
        <Html distanceFactor={10} style={{ pointerEvents: "none" }}>
          <div className="w-max max-w-[220px] rounded-md border border-border bg-surface/95 px-3 py-2 text-xs shadow-lg">
            <p className="font-semibold text-text-primary">{node.label}</p>
            <p className="text-text-muted">{node.type}</p>
            <p className="truncate text-text-muted">{node.source_file}</p>
          </div>
        </Html>
      )}
    </group>
  );
}
