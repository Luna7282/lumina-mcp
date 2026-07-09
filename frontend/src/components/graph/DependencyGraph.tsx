import { useMemo, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import type { CodebaseGraph, GraphNode as GraphNodeType } from "../../api/types";
import { computeLayout } from "./layout";
import GraphNode from "./GraphNode";
import GraphEdge from "./GraphEdge";
import StarField from "./StarField";

interface DependencyGraphProps {
  graph: CodebaseGraph;
}

function AutoRotateControls() {
  const controlsRef = useRef<OrbitControlsImpl>(null);
  const [autoRotate, setAutoRotate] = useState(true);
  const resumeTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  return (
    <OrbitControls
      ref={controlsRef}
      autoRotate={autoRotate}
      autoRotateSpeed={0.3}
      enableDamping
      dampingFactor={0.08}
      onStart={() => {
        setAutoRotate(false);
        if (resumeTimeout.current) clearTimeout(resumeTimeout.current);
      }}
      onEnd={() => {
        if (resumeTimeout.current) clearTimeout(resumeTimeout.current);
        resumeTimeout.current = setTimeout(() => setAutoRotate(true), 3000);
      }}
    />
  );
}

export default function DependencyGraph({ graph }: DependencyGraphProps) {
  const [hoveredNode, setHoveredNode] = useState<GraphNodeType | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNodeType | null>(null);
  const [selectedCommunity, setSelectedCommunity] = useState<number | null>(null);

  const positions = useMemo(
    () => computeLayout(graph.nodes, graph.communities),
    [graph.nodes, graph.communities],
  );

  const godNodeIds = useMemo(
    () => new Set(graph.god_nodes.map((g) => g.id)),
    [graph.god_nodes],
  );

  const highlightedNodeIds = useMemo(() => {
    if (selectedCommunity !== null) {
      return new Set(
        graph.nodes
          .filter((n) => graph.communities[n.id] === selectedCommunity)
          .map((n) => n.id),
      );
    }
    if (selectedNode) {
      const connected = new Set<string>([selectedNode.id]);
      graph.edges.forEach((e) => {
        if (e.source === selectedNode.id) connected.add(e.target);
        if (e.target === selectedNode.id) connected.add(e.source);
      });
      return connected;
    }
    return null;
  }, [selectedNode, selectedCommunity, graph.nodes, graph.edges, graph.communities]);

  const handleNodeClick = (node: GraphNodeType) => {
    setSelectedCommunity(null);
    setSelectedNode((prev) => (prev?.id === node.id ? null : node));
  };

  const handleNodeDoubleClick = (node: GraphNodeType) => {
    const cid = graph.communities[node.id];
    setSelectedNode(null);
    setSelectedCommunity((prev) => (prev === cid ? null : cid));
  };

  const resetSelection = () => {
    setSelectedNode(null);
    setSelectedCommunity(null);
  };

  const communitySummary =
    selectedCommunity !== null
      ? graph.community_summary[String(selectedCommunity)]
      : null;

  return (
    <div className="relative h-full w-full">
      <Canvas
        className="!bg-black"
        camera={{ position: [0, 0, 20], fov: 55 }}
        onPointerMissed={resetSelection}
      >
        <color attach="background" args={["#000000"]} />
        <ambientLight intensity={0.5} />
        <directionalLight position={[10, 10, 10]} intensity={0.5} />

        <StarField />

        <GraphEdge
          edges={graph.edges}
          positions={positions}
          highlightedNodeIds={highlightedNodeIds}
        />

        {graph.nodes.map((node) => {
          const position = positions[node.id];
          if (!position) return null;
          const dimmed = highlightedNodeIds !== null && !highlightedNodeIds.has(node.id);
          return (
            <GraphNode
              key={node.id}
              node={node}
              position={position}
              isGodNode={godNodeIds.has(node.id)}
              dimmed={dimmed}
              isSelected={selectedNode?.id === node.id}
              onHover={setHoveredNode}
              onClick={handleNodeClick}
              onDoubleClick={handleNodeDoubleClick}
            />
          );
        })}

        <AutoRotateControls />
      </Canvas>

      {(selectedNode || communitySummary) && (
        <div className="absolute bottom-4 left-4 right-4 max-h-40 overflow-y-auto rounded-lg border border-border bg-surface/95 p-4 text-sm backdrop-blur-sm">
          {selectedNode && (
            <>
              <p className="font-semibold text-text-primary">{selectedNode.label}</p>
              <p className="mb-1 text-xs uppercase tracking-wide text-accent">
                {selectedNode.type}
              </p>
              <p className="mb-1 text-text-muted">{selectedNode.source_file}</p>
              {selectedNode.docstring && (
                <p className="text-text-muted">{selectedNode.docstring}</p>
              )}
            </>
          )}
          {communitySummary && (
            <>
              <p className="font-semibold text-text-primary">
                Community {selectedCommunity} · {communitySummary.size} nodes
              </p>
              <p className="text-text-muted">
                Top nodes: {communitySummary.top_nodes.slice(0, 6).join(", ")}
              </p>
              <p className="truncate text-text-muted">
                Files: {communitySummary.files.slice(0, 4).join(", ")}
              </p>
            </>
          )}
        </div>
      )}

      {!hoveredNode && !selectedNode && !communitySummary && (
        <div className="pointer-events-none absolute bottom-4 left-4 text-xs text-text-muted">
          Drag to rotate · Scroll to zoom · Click a node for details · Double-click for community
        </div>
      )}
    </div>
  );
}
