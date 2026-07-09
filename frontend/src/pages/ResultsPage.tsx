import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { createPackage, getCodebase, getPackageStatus } from "../api/client";
import DependencyGraph from "../components/graph/DependencyGraph";
import GraphInfo from "../components/graph/GraphInfo";
import VideoList from "../components/videos/VideoList";
import GenerateButton from "../components/videos/GenerateButton";
import DocList from "../components/docs/DocList";
import LoadingSpinner from "../components/layout/LoadingSpinner";

type Tab = "videos" | "docs" | "graph-info";

export default function ResultsPage() {
  const { codebaseId } = useParams<{ codebaseId: string }>();
  const [tab, setTab] = useState<Tab>("videos");
  const [packageId, setPackageId] = useState<string | null>(null);

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

  if (codebaseQuery.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingSpinner size="lg" label="Loading codebase…" />
      </div>
    );
  }

  if (codebaseQuery.isError || !codebaseQuery.data) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-error">
          Failed to load codebase: {(codebaseQuery.error as Error)?.message}
        </p>
      </div>
    );
  }

  const { graph, name } = codebaseQuery.data;
  const pkg = packageQuery.data;
  const isGenerating =
    packageMutation.isPending || pkg?.status === "generating";

  return (
    <main className="flex h-screen flex-col pt-14">
      <div className="flex flex-1 overflow-hidden">
        {/* Left: 3D graph */}
        <div className="w-[55%] border-r border-border">
          <DependencyGraph graph={graph} />
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
                  ["graph-info", "Graph Info"],
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

            {tab === "graph-info" && <GraphInfo graph={graph} />}
          </div>
        </div>
      </div>
    </main>
  );
}
