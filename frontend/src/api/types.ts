export interface GraphNode {
  id: string;
  label: string;
  type:
    | "module"
    | "class"
    | "function"
    | "method"
    | "import"
    | "route"
    | "model";
  source_file: string;
  source_location: string;
  docstring: string;
  language: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: "calls" | "imports" | "inherits" | "contains" | "handles" | "implements";
  confidence: "EXTRACTED" | "INFERRED" | "AMBIGUOUS";
}

export interface GodNode {
  id: string;
  label: string;
  degree: number;
  type: string;
  source_file: string;
}

export interface CommunitySummary {
  size: number;
  top_nodes: string[];
  files: string[];
}

export interface CodebaseGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  communities: Record<string, number>;
  community_summary: Record<string, CommunitySummary>;
  god_nodes: GodNode[];
  language_summary: Record<string, number>;
  file_hashes: Record<string, string>;
}

export interface AnalyzeResponse {
  codebase_id: string;
  name: string;
  file_count: number;
  node_count: number;
  edge_count: number;
  god_nodes: GodNode[];
  community_count: number;
  language_summary: Record<string, number>;
  cached: boolean;
  graph: CodebaseGraph;
}

export interface VideoStatus {
  video_id: string;
  status: "rendering" | "done" | "error";
  video_url: string | null;
  output_urls: string[];
  focus: string;
  codebase_id: string;
  created_at: string;
}

export interface DocItem {
  doc_type: string;
  filename: string;
  content: string | null;
  status: "pending" | "done" | "error";
  word_count: number;
  folder?: string | null;
}

export interface PackageVideo {
  focus: string;
  scene_name: string;
  video_url: string | null;
  output_urls: string[];
  status: string;
  is_overview: boolean;
  folder: string | null;
}

export interface PackageStatus {
  package_id: string;
  status: "generating" | "done" | "partial" | "error";
  codebase_id: string;
  package_type: string;
  videos: PackageVideo[];
  docs: DocItem[];
  created_at: string;
  completed_at: string | null;
}
