import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ForceGraph3D from "react-force-graph-3d";
import type { ForceGraphMethods, NodeObject, LinkObject } from "react-force-graph-3d";
import * as THREE from "three";
import SpriteText from "three-spritetext";
import type { CodebaseGraph, GraphEdge } from "../../api/types";
import { NODE_COLORS, EDGE_OPACITY, nodeColor } from "./colors";

export type HighlightMode = "node" | "community" | "language" | null;

interface DependencyGraphProps {
  graph: CodebaseGraph;
  // Selection state from parent
  highlightedNodes: Set<string>;
  highlightedCommunity: number | null;
  highlightMode: HighlightMode;
  activeRelations: Set<GraphEdge["relation"]>;
  // Callbacks to parent
  onNodeClick: (nodeId: string) => void;
  onNodeHover: (nodeId: string | null) => void;
  onBackgroundClick: () => void;
  // Camera control from parent
  focusNodeId: string | null;
}

interface GraphNode3D {
  id: string;
  label: string;
  type: CodebaseGraph["nodes"][number]["type"];
  source_file: string;
  docstring: string;
  language: string;
  community: number;
  isGodNode: boolean;
  degree: number;
  val: number;
}

interface GraphLink3D {
  relation: GraphEdge["relation"];
  confidence: GraphEdge["confidence"];
}

type N = NodeObject<GraphNode3D>;
type L = LinkObject<GraphNode3D, GraphLink3D>;

const COMMUNITY_COLORS = [
  "#7c3aed", "#2563eb", "#059669", "#d97706",
  "#dc2626", "#db2777", "#0891b2", "#65a30d",
];

const LINK_COLORS: Record<GraphEdge["relation"], string> = {
  calls: "79,156,249",
  imports: "103,232,164",
  inherits: "192,132,252",
  handles: "249,165,79",
  contains: "107,114,128",
  implements: "56,189,248",
};

const LINK_WIDTH: Record<GraphEdge["confidence"], number> = {
  EXTRACTED: 0.8,
  INFERRED: 0.4,
  AMBIGUOUS: 0.2,
};

function linkEndpointId(endpoint: string | number | N | undefined): string | undefined {
  if (endpoint == null) return undefined;
  return typeof endpoint === "object" ? endpoint.id : String(endpoint);
}

export default function DependencyGraph({
  graph,
  highlightedNodes,
  highlightedCommunity,
  highlightMode,
  activeRelations,
  onNodeClick,
  onNodeHover,
  onBackgroundClick,
  focusNodeId,
}: DependencyGraphProps) {
  const fgRef = useRef<ForceGraphMethods<GraphNode3D, GraphLink3D>>();
  const containerRef = useRef<HTMLDivElement>(null);

  // ForceGraph3D defaults to window.innerWidth/innerHeight when no width/
  // height prop is given — it doesn't measure its containing element. Left
  // unset, the canvas renders far wider than this 55%-width column and its
  // (mostly transparent) overflow sits in front of the right-hand panel for
  // pointer-event purposes, silently swallowing clicks there even though
  // the panel visually paints on top. Track the actual container size and
  // pass it through explicitly.
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return;
      setDimensions({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Convert Lumina graph schema to react-force-graph format. Node objects
  // are memoized on `graph` alone (not activeRelations) since 3d-force-graph
  // mutates these exact objects with live x/y/z/vx/vy/vz as the simulation
  // runs — recreating them on every filter toggle would reset the layout.
  const nodes = useMemo<N[]>(() => {
    const godNodeDegrees = Object.fromEntries(graph.god_nodes.map((n) => [n.id, n.degree]));
    const godNodeIds = new Set(graph.god_nodes.map((n) => n.id));

    return graph.nodes.map((node) => ({
      id: node.id,
      label: node.label,
      type: node.type,
      source_file: node.source_file,
      docstring: node.docstring,
      language: node.language,
      community: graph.communities[node.id] ?? 0,
      isGodNode: godNodeIds.has(node.id),
      degree: godNodeDegrees[node.id] ?? 1,
      val: godNodeIds.has(node.id) ? Math.max(4, godNodeDegrees[node.id] / 3) : 1,
    }));
  }, [graph]);

  const links = useMemo<L[]>(
    () =>
      graph.edges
        .filter((e) => e.source !== e.target && activeRelations.has(e.relation))
        .map((e) => ({
          source: e.source,
          target: e.target,
          relation: e.relation,
          confidence: e.confidence,
        })),
    [graph, activeRelations],
  );

  const graphData = useMemo(() => ({ nodes, links }), [nodes, links]);

  const getNodeHighlight = useCallback(
    (node: GraphNode3D): "normal" | "highlighted" | "dimmed" => {
      if (highlightMode === null) return "normal";
      if (highlightedNodes.has(node.id)) return "highlighted";
      return "dimmed";
    },
    [highlightedNodes, highlightMode],
  );

  // Custom 3D node object — glowing sphere, optionally ringed + labeled.
  //
  // Deliberately does NOT depend on hover state. react-force-graph-3d
  // treats a change in the `nodeThreeObject` accessor's identity as a
  // signal to clear its whole node-object cache and rebuild every node's
  // geometry/materials from scratch (see nodeDataMapper.clear() in
  // three-forcegraph's digest cycle). Hovering fires far more often than
  // clicking/searching — wiring it in here made the entire graph rebuild
  // on every mouseover, which is what made the whole view feel laggy.
  // Hover feedback is handled separately via the lightweight built-in
  // `nodeLabel` tooltip instead (see the JSX below).
  const nodeThreeObject = useCallback(
    (node: N) => {
      const highlight = getNodeHighlight(node);

      const group = new THREE.Group();

      const coreGeo = new THREE.SphereGeometry(node.isGodNode ? 4 : 2, 10, 8);
      const baseColor = node.isGodNode ? "#ffffff" : nodeColor(node.type);

      const opacity = highlight === "dimmed" ? 0.08 : 1.0;
      const emissiveIntensity = highlight === "highlighted" ? 0.8 : node.isGodNode ? 0.3 : 0.1;

      const coreMat = new THREE.MeshPhongMaterial({
        color: baseColor,
        emissive: baseColor,
        emissiveIntensity,
        transparent: true,
        opacity,
      });
      group.add(new THREE.Mesh(coreGeo, coreMat));

      const ringColor =
        highlight === "highlighted" && highlightMode === "community"
          ? COMMUNITY_COLORS[node.community % COMMUNITY_COLORS.length]
          : "#f59e0b";

      // Outer glow sphere for god nodes and highlighted nodes
      if (node.isGodNode || highlight === "highlighted") {
        const glowGeo = new THREE.SphereGeometry(node.isGodNode ? 7 : 4, 10, 8);
        const glowMat = new THREE.MeshPhongMaterial({
          color: highlight === "highlighted" ? ringColor : node.isGodNode ? "#ffffff" : baseColor,
          emissive: highlight === "highlighted" ? ringColor : baseColor,
          emissiveIntensity: 0.3,
          transparent: true,
          opacity: 0.08,
          side: THREE.BackSide,
        });
        group.add(new THREE.Mesh(glowGeo, glowMat));
      }

      // Pulsing ring for highlighted nodes
      if (highlight === "highlighted") {
        const ringGeo = new THREE.RingGeometry(5, 6, 24);
        const ringMat = new THREE.MeshBasicMaterial({
          color: ringColor,
          transparent: true,
          opacity: 0.6,
          side: THREE.DoubleSide,
        });
        const ring = new THREE.Mesh(ringGeo, ringMat);
        ring.rotation.x = Math.PI / 2;
        group.add(ring);
      }

      // Sprite text label for god nodes (static — doesn't churn on hover)
      if (node.isGodNode) {
        const sprite = new SpriteText(node.label);
        sprite.color = highlight === "dimmed" ? "#374151" : "#ffffff";
        sprite.textHeight = 3;
        sprite.backgroundColor = "rgba(0,0,0,0.6)";
        sprite.padding = 1;
        sprite.borderRadius = 2;
        sprite.position.y = 7;
        group.add(sprite);
      }

      return group;
    },
    [getNodeHighlight, highlightMode],
  );

  const getLinkColor = useCallback(
    (link: L) => {
      const alpha = EDGE_OPACITY[link.confidence];

      if (highlightMode !== null) {
        const srcHighlighted = highlightedNodes.has(linkEndpointId(link.source) ?? "");
        const tgtHighlighted = highlightedNodes.has(linkEndpointId(link.target) ?? "");
        if (!srcHighlighted && !tgtHighlighted) return "rgba(100,100,100,0.03)";
        return `rgba(245,158,11,${Math.max(alpha, 0.4)})`;
      }

      return `rgba(${LINK_COLORS[link.relation]},${alpha})`;
    },
    [highlightMode, highlightedNodes],
  );

  // Camera: zoom to focused node once it has a settled position
  useEffect(() => {
    const fg = fgRef.current;
    if (!focusNodeId || !fg) return;
    const node = graphData.nodes.find((n) => n.id === focusNodeId);
    if (!node) return;

    const x = node.x ?? 0;
    const y = node.y ?? 0;
    const z = node.z ?? 0;

    fg.cameraPosition({ x, y, z: z + 80 }, { x, y, z }, 1500);
  }, [focusNodeId, graphData.nodes]);

  // Custom d3 force: pull nodes toward a per-community position on a ring,
  // so Leiden clusters read as visually distinct clumps in 3D space.
  //
  // Registering the force only touches the persistent d3ForceLayout object,
  // which is safe at any time — but do NOT also call d3ReheatSimulation()
  // here. That forces engineRunning=true immediately, and if this effect
  // fires before react-force-graph-3d's own internal digest cycle has run
  // at least once (it initializes `state.layout` from the graphData prop
  // asynchronously, not synchronously with React's render), the next
  // animation frame calls state.layout.tick() while state.layout is still
  // undefined — throwing, killing the WebGL context, and leaving a black
  // canvas. The initial graphData load already reheats the simulation on
  // its own, so no manual reheat is needed here.
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    const communityCount = Math.max(Object.keys(graph.community_summary).length, 1);

    fg.d3Force("community", (alpha: number) => {
      for (const node of graphData.nodes) {
        const angle = (node.community / communityCount) * 2 * Math.PI;
        const radius = 80;
        const cx = radius * Math.cos(angle);
        const cy = radius * Math.sin(angle);
        const strength = 0.03 * alpha;
        node.vx = (node.vx ?? 0) + (cx - (node.x ?? 0)) * strength;
        node.vy = (node.vy ?? 0) + (cy - (node.y ?? 0)) * strength;
        node.vz = (node.vz ?? 0) + (0 - (node.z ?? 0)) * strength * 0.5;
      }
    });
  }, [graphData.nodes, graph.community_summary]);

  return (
    <div ref={containerRef} className="relative h-full w-full bg-black">
      <ForceGraph3D<GraphNode3D, GraphLink3D>
        ref={fgRef}
        width={dimensions.width || undefined}
        height={dimensions.height || undefined}
        graphData={graphData}
        backgroundColor="#000000"
        nodeThreeObject={nodeThreeObject}
        nodeThreeObjectExtend={false}
        nodeLabel={(node) => node.label}
        linkColor={getLinkColor}
        linkWidth={(link) => LINK_WIDTH[link.confidence]}
        linkOpacity={0.6}
        // Straight lines use a cheap ~6-segment cylinder per edge. Any
        // nonzero curvature switches every link to a TubeGeometry sampled
        // at 30 path segments — ~30x the geometry for a purely cosmetic
        // curve, and it scales with edge count. Not worth it past a
        // handful of edges.
        linkCurvature={0}
        linkDirectionalParticles={(link) =>
          link.relation === "calls" ? 3 : link.relation === "handles" ? 2 : link.relation === "imports" ? 1 : 0
        }
        linkDirectionalParticleWidth={1.5}
        linkDirectionalParticleSpeed={0.006}
        linkDirectionalParticleColor={(link) =>
          link.relation === "calls" ? "#4f9cf9" : link.relation === "handles" ? "#f9a54f" : "#67e8a4"
        }
        d3AlphaDecay={0.02}
        d3VelocityDecay={0.3}
        onNodeClick={(node) => onNodeClick(node.id)}
        onNodeHover={(node) => {
          onNodeHover(node?.id ?? null);
          document.body.style.cursor = node ? "pointer" : "default";
        }}
        onBackgroundClick={onBackgroundClick}
        enableNodeDrag
        enableNavigationControls
        showNavInfo={false}
        rendererConfig={{ antialias: true, alpha: true }}
      />

      {/* HUD overlay — stats in corner */}
      <div className="pointer-events-none absolute left-3 top-3 space-y-1 rounded-lg bg-black/70 p-2 text-xs text-gray-400">
        <div>{graphData.nodes.length} nodes</div>
        <div>{graphData.links.length} edges</div>
        {highlightMode && <div className="text-yellow-400">{highlightedNodes.size} selected</div>}
      </div>

      {/* Legend */}
      <div className="pointer-events-none absolute bottom-3 left-3 space-y-1 rounded-lg bg-black/70 p-2 text-xs">
        {Object.entries(NODE_COLORS).map(([type, color]) => (
          <div key={type} className="flex items-center gap-1.5">
            <div className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-gray-400">{type}</span>
          </div>
        ))}
        <div className="flex items-center gap-1.5">
          <div className="h-2 w-2 rounded-full border border-gray-400 bg-white" />
          <span className="text-gray-400">god node</span>
        </div>
      </div>
    </div>
  );
}
