import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { createPackage, getCodebase, getPackageStatus } from "../api/client";
import type { GraphEdge, GraphNode } from "../api/types";
import DependencyGraph from "../components/graph/DependencyGraph";
import type { HighlightMode } from "../components/graph/DependencyGraph";
import GraphInfo from "../components/graph/GraphInfo";
import NodeDetailPanel from "../components/graph/NodeDetailPanel";
import VideoList from "../components/videos/VideoList";
import GenerateButton from "../components/videos/GenerateButton";
import DocList from "../components/docs/DocList";
import LoadingSpinner from "../components/layout/LoadingSpinner";

type Tab = "videos" | "docs" | "info";

const ALL_RELATIONS: GraphEdge["relation"][] = [
  "calls",
  "imports",
  "inherits",
  "handles",
  "contains",
  "implements",
];

export default function ResultsPage() {
  const { codebaseId } = useParams<{ codebaseId: string }>();
  const [tab, setTab] = useState<Tab>("info");
  const [packageId, setPackageId] = useState<string | null>(null);

  // Bidirectional sync state — shared between the 3D graph and the right panel.
  const [highlightedNodes, setHighlightedNodes] = useState<Set<string>>(new Set());
  const [highlightedCommunity, setHighlightedCommunity] = useState<number | null>(null);
  const [highlightMode, setHighlightMode] = useState<HighlightMode>(null);
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [nodeSearch, setNodeSearch] = useState("");
  const [activeRelations, setActiveRelations] = useState<Set<GraphEdge["relation"]>>(
    () => new Set(ALL_RELATIONS),
  );

  const codebaseQuery = useQuery({
    queryKey: ["codebase", codebaseId],
    queryFn: () => getCodebase(codebaseId!),
    enabled: !!codebaseId,
  });

  const packageQuery = useQuery({
    queryKey: ["package", packageId],
    queryFn: () => getPackageStatus(packageId!),
    enabled: !!packageId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "generating" ? 5000 : false;
    },
  });

  const packageMutation = useMutation({
    mutationFn: ({
      packageType,
      customInstructions,
    }: {
      packageType: string;
      customInstructions: string;
    }) =>
      createPackage(
        codebaseId!,
        packageType,
        customInstructions.trim() || undefined,
      ),
    onSuccess: (result) => setPackageId(result.package_id),
  });

  const graph = codebaseQuery.data?.graph;

  const clearSelection = () => {
    setHighlightedNodes(new Set());
    setHighlightedCommunity(null);
    setHighlightMode(null);
    setFocusNodeId(null);
    setSelectedNode(null);
  };

  const handleNodeClick = (nodeId: string) => {
    if (!graph) return;
    const node = graph.nodes.find((n) => n.id === nodeId);
    if (!node) return;

    // Toggle: clicking the already-pinned node deselects it.
    if (selectedNode?.id === nodeId) {
      clearSelection();
      return;
    }

    setSelectedNode(node);
    setHighlightedNodes(new Set([nodeId]));
    setHighlightedCommunity(null);
    setHighlightMode("node");
    setFocusNodeId(nodeId);
    setNodeSearch("");
    setTab("info");
  };

  // Hover preview: moves the camera and, if nothing else is highlighted,
  // glows the node too. A click always takes precedence over hover, and an
  // active search/community/language highlight is never clobbered by a
  // passing mouseover.
  const handleNodeHover = (nodeId: string | null) => {
    if (selectedNode) return;

    if (!nodeId) {
      setFocusNodeId(null);
      if (highlightMode === "node" && !nodeSearch.trim()) {
        setHighlightedNodes(new Set());
        setHighlightMode(null);
      }
      return;
    }

    setFocusNodeId(nodeId);
    if (highlightMode === null) {
      setHighlightedNodes(new Set([nodeId]));
      setHighlightMode("node");
    }
  };

  const highlightCommunity = (communityId: number) => {
    if (!graph) return;
    if (highlightedCommunity === communityId) {
      clearSelection();
      return;
    }
    const members = graph.nodes
      .filter((n) => graph.communities[n.id] === communityId)
      .map((n) => n.id);

    setSelectedNode(null);
    setNodeSearch("");
    setHighlightedNodes(new Set(members));
    setHighlightedCommunity(communityId);
    setHighlightMode("community");
    setFocusNodeId(members[0] ?? null);
  };

  const highlightLanguage = (language: string) => {
    if (!graph) return;
    const members = graph.nodes.filter((n) => n.language === language).map((n) => n.id);

    setSelectedNode(null);
    setNodeSearch("");
    setHighlightedNodes(new Set(members));
    setHighlightedCommunity(null);
    setHighlightMode("language");
    setFocusNodeId(null);
  };

  const highlightFile = (filePath: string) => {
    if (!graph) return;
    const members = graph.nodes.filter((n) => n.source_file === filePath).map((n) => n.id);

    setSelectedNode(null);
    setNodeSearch("");
    setHighlightedNodes(new Set(members));
    setHighlightedCommunity(null);
    setHighlightMode("node");
    setFocusNodeId(members[0] ?? null);
  };

  const toggleRelation = (relation: GraphEdge["relation"]) => {
    setActiveRelations((prev) => {
      const next = new Set(prev);
      if (next.has(relation)) next.delete(relation);
      else next.add(relation);
      return next;
    });
  };

  // Live node search — matches highlight in the graph as the user types.
  useEffect(() => {
    if (!graph) return;

    if (!nodeSearch.trim()) {
      if (highlightMode === "node" && !selectedNode) {
        setHighlightedNodes(new Set());
        setHighlightMode(null);
      }
      return;
    }

    const q = nodeSearch.toLowerCase();
    const matching = new Set(
      graph.nodes
        .filter(
          (n) =>
            n.label.toLowerCase().includes(q) || n.source_file.toLowerCase().includes(q),
        )
        .map((n) => n.id),
    );
    setSelectedNode(null);
    setHighlightedNodes(matching);
    setHighlightedCommunity(null);
    setHighlightMode("node");
    // Only re-run when the search text (or graph) changes — selectedNode is
    // read purely as a guard against clobbering an already-pinned node.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeSearch, graph]);

  const getNodeEdges = (nodeId: string): GraphEdge[] =>
    graph ? graph.edges.filter((e) => e.source === nodeId || e.target === nodeId) : [];

  if (codebaseQuery.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingSpinner size="lg" label="Loading codebase…" />
      </div>
    );
  }

  if (codebaseQuery.isError || !codebaseQuery.data || !graph) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-error">
          Failed to load codebase: {(codebaseQuery.error as Error)?.message}
        </p>
      </div>
    );
  }

  const { name } = codebaseQuery.data;
  const pkg = packageQuery.data;
  const isGenerating =
    packageMutation.isPending || pkg?.status === "generating";

  return (
    <main className="flex h-screen flex-col pt-14">
      <div className="flex flex-1 overflow-hidden">
        {/* Left: 3D graph */}
        <div className="relative w-[55%] border-r border-border">
          <DependencyGraph
            graph={graph}
            highlightedNodes={highlightedNodes}
            highlightedCommunity={highlightedCommunity}
            highlightMode={highlightMode}
            activeRelations={activeRelations}
            onNodeClick={handleNodeClick}
            onNodeHover={handleNodeHover}
            onBackgroundClick={clearSelection}
            focusNodeId={focusNodeId}
          />

          {/* Search overlay on the canvas — shares state with the Graph Info tab search */}
          <div className="absolute right-3 top-3 z-10">
            <div className="flex items-center gap-2 rounded-lg border border-gray-700 bg-black/80 px-3 py-2 backdrop-blur">
              <span className="text-sm text-gray-500">⌕</span>
              <input
                type="text"
                placeholder="Search nodes…"
                value={nodeSearch}
                onChange={(e) => setNodeSearch(e.target.value)}
                className="w-40 bg-transparent text-sm text-white outline-none placeholder-gray-600"
              />
              {nodeSearch && (
                <button
                  type="button"
                  onClick={() => setNodeSearch("")}
                  className="text-xs text-gray-500 hover:text-white"
                >
                  ✕
                </button>
              )}
            </div>
            {nodeSearch && (
              <div className="mt-1 text-right text-xs text-gray-500">
                {highlightedNodes.size} matches
              </div>
            )}
          </div>

          {selectedNode && (
            <NodeDetailPanel
              node={selectedNode}
              edges={getNodeEdges(selectedNode.id)}
              communityId={graph.communities[selectedNode.id]}
              onClose={clearSelection}
              onSelectNode={handleNodeClick}
              onShowCommunity={highlightCommunity}
              onExplain={() => setTab("videos")}
            />
          )}
        </div>

        {/* Right: tabbed panel */}
        <div className="flex w-[45%] flex-col overflow-hidden">
          <div className="border-b border-border px-6 pt-4">
            <h2 className="mb-3 truncate text-lg font-semibold text-text-primary">
              {name}
            </h2>
            <div className="flex gap-1">
              {(
                [
                  ["videos", "Videos"],
                  ["docs", "Docs"],
                  ["info", "Graph Info"],
                ] as [Tab, string][]
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setTab(id)}
                  className={`rounded-t-md px-4 py-2 text-sm font-medium transition-colors ${
                    tab === id
                      ? "border-b-2 border-accent text-accent"
                      : "text-text-muted hover:text-text-primary"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-6">
            {tab === "videos" && (
              <div className="flex flex-col gap-6">
                <GenerateButton
                  isGenerating={isGenerating}
                  onGenerate={(packageType, customInstructions) =>
                    packageMutation.mutate({ packageType, customInstructions })
                  }
                />

                {packageMutation.isError && (
                  <p className="text-sm text-error">
                    {(packageMutation.error as Error).message}
                  </p>
                )}

                {isGenerating && !pkg?.videos.length && (
                  <LoadingSpinner
                    size="sm"
                    label="Generating scenes… rendering videos…"
                  />
                )}

                {pkg ? (
                  <VideoList videos={pkg.videos} />
                ) : (
                  !isGenerating && (
                    <p className="text-sm text-text-muted">
                      No package generated yet. Click "Generate Package" to
                      create explainer videos for this codebase.
                    </p>
                  )
                )}
              </div>
            )}

            {tab === "docs" && (
              <DocList codebaseId={codebaseId!} packageDocs={pkg?.docs ?? []} />
            )}

            {tab === "info" && (
              <GraphInfo
                graph={graph}
                nodeSearch={nodeSearch}
                onNodeSearchChange={setNodeSearch}
                highlightedNodes={highlightedNodes}
                highlightedCommunity={highlightedCommunity}
                highlightMode={highlightMode}
                selectedNodeId={selectedNode?.id ?? null}
                activeRelations={activeRelations}
                onToggleRelation={toggleRelation}
                onHoverNode={handleNodeHover}
                onSelectNode={handleNodeClick}
                onHighlightCommunity={highlightCommunity}
                onHighlightLanguage={highlightLanguage}
                onHighlightFile={highlightFile}
              />
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
