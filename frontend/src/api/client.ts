import type {
  AnalyzeResponse,
  CodebaseGraph,
  DocItem,
  PackageStatus,
  VideoStatus,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ? JSON.stringify(body.detail) : detail;
    } catch {
      // response wasn't JSON — fall back to statusText
    }
    throw new ApiError(res.status, detail);
  }

  return res.json() as Promise<T>;
}

export async function analyzeFiles(
  files: Record<string, string>,
  name: string,
): Promise<AnalyzeResponse> {
  const result = await request<Omit<AnalyzeResponse, "graph">>("/api/analyze", {
    method: "POST",
    body: JSON.stringify({ files, name }),
  });
  // /api/analyze doesn't return the full graph — fetch it so the caller
  // always has a complete AnalyzeResponse to hand off to the results page.
  const full = await getCodebase(result.codebase_id);
  return { ...result, graph: full.graph };
}

interface CodebaseReadResponse {
  id: string;
  name: string;
  source: string;
  content_hash: string;
  file_count: number;
  language_summary: Record<string, number>;
  graph: CodebaseGraph;
  created_at: string;
  last_analyzed_at: string;
}

export async function getCodebase(
  codebaseId: string,
): Promise<AnalyzeResponse & { graph: CodebaseGraph }> {
  const codebase = await request<CodebaseReadResponse>(
    `/api/codebase/${codebaseId}`,
  );
  const graph = codebase.graph;
  const communityCount = new Set(Object.values(graph.communities ?? {})).size;
  return {
    codebase_id: codebase.id,
    name: codebase.name,
    file_count: codebase.file_count,
    node_count: graph.nodes?.length ?? 0,
    edge_count: graph.edges?.length ?? 0,
    god_nodes: graph.god_nodes ?? [],
    community_count: communityCount,
    language_summary: codebase.language_summary,
    cached: true,
    graph,
  };
}

export async function createExplainer(
  codebaseId: string,
  focus: string,
  quality: string,
  customInstructions?: string,
): Promise<{ video_id: string; scenes: string[] }> {
  return request("/api/explain", {
    method: "POST",
    body: JSON.stringify({
      codebase_id: codebaseId,
      focus,
      quality,
      custom_instructions: customInstructions,
    }),
  });
}

export async function getVideoStatus(videoId: string): Promise<VideoStatus> {
  return request(`/api/video/${videoId}`);
}

export async function createPackage(
  codebaseId: string,
  packageType: string,
  customInstructions?: string,
): Promise<{ package_id: string }> {
  return request("/api/onboard", {
    method: "POST",
    body: JSON.stringify({
      codebase_id: codebaseId,
      package_type: packageType,
      custom_instructions: customInstructions,
    }),
  });
}

export async function getPackageStatus(
  packageId: string,
): Promise<PackageStatus> {
  return request(`/api/package/${packageId}`);
}

export async function generateDocs(
  codebaseId: string,
  docType: string,
  customInstructions?: string,
): Promise<DocItem> {
  const result = await request<{
    codebase_id: string;
    doc_type: string;
    filename: string;
    content: string;
    word_count: number;
  }>("/api/docs", {
    method: "POST",
    body: JSON.stringify({
      codebase_id: codebaseId,
      doc_type: docType,
      custom_instructions: customInstructions,
    }),
  });
  return {
    doc_type: result.doc_type,
    filename: result.filename,
    content: result.content,
    status: "done",
    word_count: result.word_count,
  };
}

export { ApiError };
