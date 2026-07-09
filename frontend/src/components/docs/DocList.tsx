import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import type { DocItem } from "../../api/types";
import { generateDocs } from "../../api/client";
import DocViewer from "./DocViewer";
import LoadingSpinner from "../layout/LoadingSpinner";

interface DocListProps {
  codebaseId: string;
  packageDocs: DocItem[];
}

const DOC_TYPES = [
  { id: "readme", label: "README" },
  { id: "architecture", label: "Architecture" },
  { id: "onboarding", label: "Onboarding" },
  { id: "api", label: "API" },
];

export default function DocList({ codebaseId, packageDocs }: DocListProps) {
  const [docType, setDocType] = useState("readme");
  const [openFolder, setOpenFolder] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => generateDocs(codebaseId, docType),
  });

  const folderDocs = packageDocs.filter((d) => d.folder);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="mb-2 text-sm text-text-muted">Doc type</p>
        <div className="mb-4 grid grid-cols-4 gap-2">
          {DOC_TYPES.map((dt) => (
            <button
              key={dt.id}
              type="button"
              onClick={() => setDocType(dt.id)}
              className={`rounded-lg border px-2 py-2 text-center text-xs font-medium transition-colors ${
                docType === dt.id
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-border text-text-muted hover:text-text-primary"
              }`}
            >
              {dt.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
          className="w-full rounded-lg bg-gradient-to-r from-accent to-purple-600 py-2.5 text-sm font-semibold text-white shadow-lg shadow-accent/20 transition-transform hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {mutation.isPending ? "Generating…" : "Generate Docs"}
        </button>
      </div>

      {mutation.isPending && <LoadingSpinner size="sm" label="Writing documentation…" />}

      {mutation.isError && (
        <p className="text-sm text-error">{(mutation.error as Error).message}</p>
      )}

      {mutation.data?.content && (
        <DocViewer filename={mutation.data.filename} content={mutation.data.content} />
      )}

      {folderDocs.length > 0 && (
        <div>
          <p className="mb-2 text-sm text-text-muted">Per-folder READMEs</p>
          <div className="flex flex-col gap-2">
            {folderDocs.map((doc) => {
              const key = `${doc.folder}-${doc.filename}`;
              const isOpen = openFolder === key;
              return (
                <div key={key} className="rounded-lg border border-border bg-surface">
                  <button
                    type="button"
                    onClick={() => setOpenFolder(isOpen ? null : key)}
                    className="flex w-full items-center justify-between px-4 py-3 text-left text-sm"
                  >
                    <span className="font-medium text-text-primary">{doc.folder}</span>
                    <span className="text-text-muted">{isOpen ? "−" : "+"}</span>
                  </button>
                  {isOpen && doc.content && (
                    <div className="border-t border-border p-4">
                      <div className="markdown-body">
                        {doc.status === "done" ? (
                          <DocViewer filename={doc.filename} content={doc.content} />
                        ) : (
                          <LoadingSpinner size="sm" label="Generating…" />
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
