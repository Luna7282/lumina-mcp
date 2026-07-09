import { useCallback, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { analyzeFiles } from "../api/client";
import { extractZip } from "../utils/zip";
import { parsePastedFiles } from "../utils/parsePastedFiles";
import ProgressBar from "../components/layout/ProgressBar";

type Tab = "zip" | "paste";

const PROGRESS_STEPS = [
  "Parsing files...",
  "Building graph...",
  "Detecting communities...",
  "Ready!",
];

const PASTE_PLACEHOLDER = `--- src/index.py ---
def main():
    print("hello")

--- src/utils.py ---
def helper():
    return 42`;

export default function AnalyzePage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("zip");
  const [projectName, setProjectName] = useState("");
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [pastedText, setPastedText] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [progressStep, setProgressStep] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      setProgressStep(0);
      let files: Record<string, string>;

      if (tab === "zip") {
        if (!zipFile) throw new Error("Select a ZIP file first");
        files = await extractZip(zipFile);
      } else {
        files = parsePastedFiles(pastedText);
      }

      if (Object.keys(files).length === 0) {
        throw new Error("No parseable code files found");
      }

      setProgressStep(1);
      await new Promise((r) => setTimeout(r, 400));
      setProgressStep(2);

      const name = projectName.trim() || "unnamed";
      const result = await analyzeFiles(files, name);

      setProgressStep(3);
      return result;
    },
    onSuccess: (result) => {
      navigate(`/results/${result.codebase_id}`);
    },
  });

  const handleFiles = useCallback((fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) return;
    const file = fileList[0];
    if (!file.name.endsWith(".zip")) return;
    setZipFile(file);
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(false);
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles],
  );

  const canSubmit =
    tab === "zip" ? zipFile !== null : pastedText.trim().length > 0;

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center px-6 pb-24 pt-32">
      <h1 className="mb-2 text-3xl font-bold text-text-primary">
        Analyze your codebase
      </h1>
      <p className="mb-10 text-center text-text-muted">
        Upload a ZIP or paste files directly — Lumina handles the rest.
      </p>

      {mutation.isPending ? (
        <div className="flex w-full flex-col items-center gap-6 rounded-xl border border-border bg-surface p-10">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-border border-t-accent" />
          <ProgressBar steps={PROGRESS_STEPS} currentStep={progressStep} />
        </div>
      ) : (
        <div className="w-full">
          {/* Tabs */}
          <div className="mb-6 flex gap-1 rounded-lg border border-border bg-surface p-1">
            <button
              type="button"
              onClick={() => setTab("zip")}
              className={`flex-1 rounded-md py-2 text-sm font-medium transition-colors ${
                tab === "zip"
                  ? "bg-accent text-white"
                  : "text-text-muted hover:text-text-primary"
              }`}
            >
              Upload ZIP
            </button>
            <button
              type="button"
              onClick={() => setTab("paste")}
              className={`flex-1 rounded-md py-2 text-sm font-medium transition-colors ${
                tab === "paste"
                  ? "bg-accent text-white"
                  : "text-text-muted hover:text-text-primary"
              }`}
            >
              Paste Files
            </button>
          </div>

          {tab === "zip" ? (
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={onDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed bg-surface px-6 py-16 text-center transition-colors ${
                isDragging ? "border-accent bg-accent/5" : "border-border"
              }`}
            >
              <svg
                width="36"
                height="36"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="text-text-muted"
              >
                <path d="M7 16a4 4 0 0 1-.88-7.9A5.5 5.5 0 0 1 17 8.5c0 .17-.01.33-.03.5A4 4 0 0 1 16 16" />
                <path d="M12 12v7M9.5 14.5 12 12l2.5 2.5" />
              </svg>
              {zipFile ? (
                <div>
                  <p className="font-medium text-text-primary">{zipFile.name}</p>
                  <p className="text-sm text-text-muted">
                    {formatBytes(zipFile.size)}
                  </p>
                </div>
              ) : (
                <div>
                  <p className="font-medium text-text-primary">
                    Drop your project ZIP here
                  </p>
                  <p className="text-sm text-text-muted">or click to browse</p>
                </div>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept=".zip"
                className="hidden"
                onChange={(e) => handleFiles(e.target.files)}
              />
            </div>
          ) : (
            <div>
              <p className="mb-2 text-xs text-text-muted">
                Format: separate each file with{" "}
                <code className="rounded bg-surface px-1 py-0.5 text-accent">
                  --- path/to/file ---
                </code>
              </p>
              <textarea
                value={pastedText}
                onChange={(e) => setPastedText(e.target.value)}
                placeholder={PASTE_PLACEHOLDER}
                rows={12}
                className="w-full resize-y rounded-lg border border-border bg-surface p-4 font-mono text-sm text-text-primary placeholder:text-text-muted/60 focus:border-accent focus:outline-none"
              />
            </div>
          )}

          <div className="mt-6">
            <label className="mb-1 block text-sm text-text-muted">
              Project name
            </label>
            <input
              type="text"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              placeholder="my-project"
              className="w-full rounded-lg border border-border bg-surface px-4 py-2.5 text-text-primary placeholder:text-text-muted/60 focus:border-accent focus:outline-none"
            />
          </div>

          {mutation.isError && (
            <p className="mt-4 text-sm text-error">
              {(mutation.error as Error).message}
            </p>
          )}

          <button
            type="button"
            disabled={!canSubmit}
            onClick={() => mutation.mutate()}
            className="mt-6 w-full rounded-lg bg-gradient-to-r from-accent to-purple-600 py-3 text-sm font-semibold text-white shadow-lg shadow-accent/20 transition-transform hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100"
          >
            Analyze →
          </button>
        </div>
      )}
    </main>
  );
}
