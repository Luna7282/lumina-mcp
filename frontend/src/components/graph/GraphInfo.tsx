import type { CodebaseGraph } from "../../api/types";

interface GraphInfoProps {
  graph: CodebaseGraph;
}

const LANGUAGE_COLORS = [
  "#4f9cf9",
  "#67e8a4",
  "#f9a54f",
  "#c084fc",
  "#f87171",
  "#facc15",
  "#38bdf8",
  "#fb7185",
];

export default function GraphInfo({ graph }: GraphInfoProps) {
  const languages = Object.entries(graph.language_summary).sort((a, b) => b[1] - a[1]);
  const maxCount = Math.max(...languages.map(([, count]) => count), 1);
  const communities = Object.entries(graph.community_summary);
  const communityCount = new Set(Object.values(graph.communities)).size;

  return (
    <div className="flex flex-col gap-8">
      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <StatCard label="Nodes" value={graph.nodes.length} />
        <StatCard label="Edges" value={graph.edges.length} />
        <StatCard label="Communities" value={communityCount} />
      </div>

      {/* Language summary */}
      <div>
        <h4 className="mb-3 text-sm font-semibold text-text-primary">Languages</h4>
        <div className="flex flex-col gap-2">
          {languages.map(([lang, count], i) => (
            <div key={lang} className="flex items-center gap-3">
              <span className="w-20 shrink-0 text-xs text-text-muted">{lang}</span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-background">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${(count / maxCount) * 100}%`,
                    backgroundColor: LANGUAGE_COLORS[i % LANGUAGE_COLORS.length],
                  }}
                />
              </div>
              <span className="w-8 shrink-0 text-right text-xs text-text-muted">{count}</span>
            </div>
          ))}
        </div>
      </div>

      {/* God nodes */}
      <div>
        <h4 className="mb-3 text-sm font-semibold text-text-primary">
          Architectural hubs
        </h4>
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-left text-xs">
            <thead className="bg-background text-text-muted">
              <tr>
                <th className="px-3 py-2 font-medium">#</th>
                <th className="px-3 py-2 font-medium">Name</th>
                <th className="px-3 py-2 font-medium">Type</th>
                <th className="px-3 py-2 font-medium">File</th>
                <th className="px-3 py-2 font-medium">Degree</th>
              </tr>
            </thead>
            <tbody>
              {graph.god_nodes.map((node, i) => (
                <tr key={node.id} className="border-t border-border">
                  <td className="px-3 py-2 text-text-muted">{i + 1}</td>
                  <td className="px-3 py-2 text-text-primary">{node.label}</td>
                  <td className="px-3 py-2 text-text-muted">{node.type}</td>
                  <td className="max-w-[160px] truncate px-3 py-2 text-text-muted">
                    {node.source_file}
                  </td>
                  <td className="px-3 py-2 text-text-muted">{node.degree}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Communities */}
      <div>
        <h4 className="mb-3 text-sm font-semibold text-text-primary">Communities</h4>
        <div className="grid gap-3 sm:grid-cols-2">
          {communities.map(([cid, summary]) => (
            <div key={cid} className="rounded-lg border border-border bg-surface p-4">
              <p className="mb-1 text-sm font-semibold text-text-primary">
                Community {cid} · {summary.size} nodes
              </p>
              <p className="mb-1 truncate text-xs text-text-muted">
                {summary.top_nodes.slice(0, 5).join(", ")}
              </p>
              <p className="truncate text-xs text-text-muted">
                {summary.files.slice(0, 3).join(", ")}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4 text-center">
      <p className="text-2xl font-bold text-text-primary">{value}</p>
      <p className="text-xs text-text-muted">{label}</p>
    </div>
  );
}
