import { useMemo, useRef, type RefObject } from "react";
import type { CodebaseGraph, GraphEdge, GraphNode } from "../../api/types";
import type { HighlightMode } from "./DependencyGraph";
import { nodeColor } from "./colors";

interface GraphInfoProps {
  graph: CodebaseGraph;
  nodeSearch: string;
  onNodeSearchChange: (value: string) => void;
  highlightedNodes: Set<string>;
  highlightedCommunity: number | null;
  highlightMode: HighlightMode;
  selectedNodeId: string | null;
  activeRelations: Set<GraphEdge["relation"]>;
  onToggleRelation: (relation: GraphEdge["relation"]) => void;
  onHoverNode: (nodeId: string | null) => void;
  onSelectNode: (nodeId: string) => void;
  onHighlightCommunity: (communityId: number) => void;
  onHighlightLanguage: (language: string) => void;
  onHighlightFile: (filePath: string) => void;
}

const LANGUAGE_COLORS = [
  "#4f9cf9", "#67e8a4", "#f9a54f", "#c084fc",
  "#f87171", "#facc15", "#38bdf8", "#fb7185",
];

const COMMUNITY_COLORS = [
  "#7c3aed", "#2563eb", "#059669", "#d97706",
  "#dc2626", "#db2777", "#0891b2", "#65a30d",
];

const RELATION_COLORS: Record<GraphEdge["relation"], string> = {
  calls: "text-blue-400",
  imports: "text-green-400",
  inherits: "text-purple-400",
  handles: "text-orange-400",
  contains: "text-gray-400",
  implements: "text-cyan-400",
};

const RELATION_DOT_COLORS: Record<GraphEdge["relation"], string> = {
  calls: "#4f9cf9",
  imports: "#67e8a4",
  inherits: "#c084fc",
  handles: "#f9a54f",
  contains: "#9ca3af",
  implements: "#38bdf8",
};

const ALL_RELATIONS: GraphEdge["relation"][] = [
  "calls", "imports", "inherits", "handles", "contains", "implements",
];

function scrollToSection(ref: RefObject<HTMLDivElement>) {
  ref.current?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export default function GraphInfo({
  graph,
  nodeSearch,
  onNodeSearchChange,
  highlightedNodes,
  highlightedCommunity,
  highlightMode,
  selectedNodeId,
  activeRelations,
  onToggleRelation,
  onHoverNode,
  onSelectNode,
  onHighlightCommunity,
  onHighlightLanguage,
  onHighlightFile,
}: GraphInfoProps) {
  const languages = Object.entries(graph.language_summary).sort((a, b) => b[1] - a[1]);
  const maxLangCount = Math.max(...languages.map(([, count]) => count), 1);
  const communities = Object.entries(graph.community_summary).sort(
    (a, b) => b[1].size - a[1].size,
  );
  const communityCount = new Set(Object.values(graph.communities)).size;
  const maxCommunitySize = Math.max(...communities.map(([, c]) => c.size), 1);

  const relationCounts = useMemo(() => {
    const counts = new Map<GraphEdge["relation"], number>();
    for (const edge of graph.edges) {
      counts.set(edge.relation, (counts.get(edge.relation) ?? 0) + 1);
    }
    return counts;
  }, [graph.edges]);

  const fileNodeCounts = useMemo(() => {
    const map = new Map<string, { count: number; language: string }>();
    for (const node of graph.nodes) {
      const existing = map.get(node.source_file);
      if (existing) existing.count += 1;
      else map.set(node.source_file, { count: 1, language: node.language });
    }
    return map;
  }, [graph.nodes]);

  const folderGroups = useMemo(() => {
    const groups = new Map<string, string[]>();
    for (const file of fileNodeCounts.keys()) {
      const parts = file.split("/");
      const folder = parts.length > 1 ? parts[0] : "(root)";
      const list = groups.get(folder) ?? [];
      list.push(file);
      groups.set(folder, list);
    }
    return [...groups.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [fileNodeCounts]);

  const nodesByLabel = useMemo(() => {
    const map = new Map<string, string>();
    for (const node of graph.nodes) if (!map.has(node.label)) map.set(node.label, node.id);
    return map;
  }, [graph.nodes]);

  const statsRef = useRef<HTMLDivElement>(null);
  const languagesRef = useRef<HTMLDivElement>(null);
  const communitiesRef = useRef<HTMLDivElement>(null);
  const godNodesRef = useRef<HTMLDivElement>(null);
  const filesRef = useRef<HTMLDivElement>(null);

  const searchActive = highlightMode === "node" && nodeSearch.trim().length > 0;

  return (
    <div className="flex flex-col gap-8">
      {/* Search */}
      <div>
        <div className="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2">
          <span className="text-sm text-text-muted">⌕</span>
          <input
            type="text"
            placeholder="Search nodes by name or file…"
            value={nodeSearch}
            onChange={(e) => onNodeSearchChange(e.target.value)}
            className="w-full bg-transparent text-sm text-text-primary outline-none placeholder-text-muted"
          />
          {nodeSearch && (
            <button
              type="button"
              onClick={() => onNodeSearchChange("")}
              className="text-xs text-text-muted hover:text-text-primary"
            >
              ✕
            </button>
          )}
        </div>
        {searchActive && (
          <p className="mt-1 text-xs text-text-muted">{highlightedNodes.size} nodes match</p>
        )}
      </div>

      {/* Stats */}
      <div ref={statsRef} className="grid grid-cols-2 gap-3">
        <StatCard label="Nodes" value={graph.nodes.length} onClick={() => scrollToSection(godNodesRef)} />
        <StatCard label="Edges" value={graph.edges.length} onClick={() => scrollToSection(filesRef)} />
        <StatCard
          label="Languages"
          value={languages.length}
          onClick={() => scrollToSection(languagesRef)}
        />
        <StatCard
          label="Communities"
          value={communityCount}
          onClick={() => scrollToSection(communitiesRef)}
        />
      </div>

      {/* God nodes */}
      <div ref={godNodesRef}>
        <h4 className="text-sm font-semibold text-text-primary">⬡ Architectural Hubs</h4>
        <p className="mb-3 text-xs text-text-muted">Most connected components</p>
        <div className="flex flex-col gap-1">
          {graph.god_nodes.map((node) => {
            const active = highlightedNodes.has(node.id) && highlightMode !== null;
            return (
              <div
                key={node.id}
                onMouseEnter={() => onHoverNode(node.id)}
                onMouseLeave={() => onHoverNode(null)}
                onClick={() => onSelectNode(node.id)}
                className={`group flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-xs transition-colors ${
                  active
                    ? "border-l-2 border-yellow-400 bg-yellow-900/10"
                    : "border-l-2 border-transparent hover:bg-white/5"
                }`}
              >
                <div
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: nodeColor(node.type as GraphNode["type"]) }}
                />
                <span className="shrink-0 font-medium text-text-primary">{node.label}</span>
                <span className="truncate text-text-muted">{node.source_file}</span>
                <span className="ml-auto shrink-0 rounded bg-background px-1.5 py-0.5 text-text-muted">
                  {node.degree}
                </span>
                <span className="hidden shrink-0 text-accent group-hover:inline">
                  Focus in graph →
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Communities */}
      <div ref={communitiesRef}>
        <h4 className="text-sm font-semibold text-text-primary">⬡ Code Communities</h4>
        <p className="mb-3 text-xs text-text-muted">Leiden clustering groups</p>
        <div className="grid gap-3 sm:grid-cols-2">
          {communities.map(([cid, summary]) => {
            const communityId = Number(cid);
            const active = highlightedCommunity === communityId;
            const color = COMMUNITY_COLORS[communityId % COMMUNITY_COLORS.length];
            return (
              <div
                key={cid}
                onClick={() => onHighlightCommunity(communityId)}
                className={`cursor-pointer rounded-lg border p-3 transition-colors ${
                  active ? "border-purple-400 ring-1 ring-purple-400" : "border-border hover:border-text-muted"
                } bg-surface`}
              >
                <div className="mb-1 flex items-center gap-2">
                  <div className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: color }} />
                  <p className="text-sm font-semibold text-text-primary">
                    Community {cid} · {summary.size} nodes
                  </p>
                </div>
                <div className="mb-2 h-1.5 overflow-hidden rounded-full bg-background">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${(summary.size / maxCommunitySize) * 100}%`, backgroundColor: color }}
                  />
                </div>
                <div className="mb-1 flex flex-wrap gap-1">
                  {summary.top_nodes.slice(0, 6).map((label) => {
                    const nodeId = nodesByLabel.get(label);
                    return (
                      <button
                        key={label}
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (nodeId) onSelectNode(nodeId);
                        }}
                        className="rounded bg-background px-1.5 py-0.5 text-xs text-text-muted hover:text-accent"
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
                <p className="truncate text-xs text-text-muted">{summary.files.slice(0, 3).join(", ")}</p>
              </div>
            );
          })}
        </div>
      </div>

      {/* Languages */}
      <div ref={languagesRef}>
        <h4 className="mb-3 text-sm font-semibold text-text-primary">Languages</h4>
        <div className="flex flex-col gap-2">
          {languages.map(([lang, count], i) => {
            const active = highlightMode === "language" && highlightedNodes.size > 0 && highlightedNodes.has(
              graph.nodes.find((n) => n.language === lang)?.id ?? "",
            );
            const color = LANGUAGE_COLORS[i % LANGUAGE_COLORS.length];
            return (
              <div
                key={lang}
                onClick={() => onHighlightLanguage(lang)}
                className={`flex cursor-pointer items-center gap-3 rounded-md px-1 py-1 transition-colors ${
                  active ? "bg-white/5" : "hover:bg-white/5"
                }`}
              >
                <span className="w-20 shrink-0 text-xs text-text-muted">{lang}</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-background">
                  <div
                    className="h-full rounded-full transition-opacity"
                    style={{
                      width: `${(count / maxLangCount) * 100}%`,
                      backgroundColor: color,
                      opacity: active ? 1 : 0.75,
                      boxShadow: active ? `0 0 6px ${color}` : "none",
                    }}
                  />
                </div>
                <span className="w-8 shrink-0 text-right text-xs text-text-muted">{count}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* File tree */}
      <div ref={filesRef}>
        <h4 className="mb-3 text-sm font-semibold text-text-primary">File Tree</h4>
        <div className="flex flex-col gap-3">
          {folderGroups.map(([folder, files]) => (
            <div key={folder}>
              <p className="mb-1 text-xs font-medium text-text-primary">
                {folder}/ <span className="text-text-muted">({files.length} files)</span>
              </p>
              <div className="flex flex-col gap-0.5 border-l border-border pl-3">
                {files.map((file) => {
                  const meta = fileNodeCounts.get(file)!;
                  const active = highlightedNodes.has(
                    graph.nodes.find((n) => n.source_file === file)?.id ?? "",
                  );
                  return (
                    <div
                      key={file}
                      onClick={() => onHighlightFile(file)}
                      className={`flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-xs transition-colors ${
                        active ? "bg-accent/10 text-accent" : "text-text-muted hover:bg-white/5 hover:text-text-primary"
                      }`}
                    >
                      <span className="truncate">{file.split("/").pop()}</span>
                      <span className="shrink-0 text-text-muted">[{meta.count} nodes]</span>
                      <span className="ml-auto shrink-0">→</span>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Edge filters */}
      <div>
        <h4 className="mb-3 text-sm font-semibold text-text-primary">Edge Types</h4>
        <div className="flex flex-col gap-1">
          {ALL_RELATIONS.filter((rel) => (relationCounts.get(rel) ?? 0) > 0).map((rel) => {
            const on = activeRelations.has(rel);
            return (
              <label
                key={rel}
                className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-xs hover:bg-white/5"
              >
                <input
                  type="checkbox"
                  checked={on}
                  onChange={() => onToggleRelation(rel)}
                  className="accent-accent"
                />
                <div
                  className="h-2 w-2 rounded-full"
                  style={{ backgroundColor: RELATION_DOT_COLORS[rel], opacity: on ? 1 : 0.3 }}
                />
                <span className={on ? RELATION_COLORS[rel] : "text-text-muted"}>{rel}</span>
                <span className="ml-auto text-text-muted">{relationCounts.get(rel) ?? 0} edges</span>
              </label>
            );
          })}
        </div>
      </div>

      {selectedNodeId && (
        <p className="text-xs text-text-muted">
          Selected node highlighted below the graph — click it again to deselect.
        </p>
      )}
    </div>
  );
}

function StatCard({ label, value, onClick }: { label: string; value: number; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-lg border border-border bg-surface p-4 text-center transition-colors hover:border-accent"
    >
      <p className="text-2xl font-bold text-text-primary">{value}</p>
      <p className="text-xs text-text-muted">{label}</p>
    </button>
  );
}
