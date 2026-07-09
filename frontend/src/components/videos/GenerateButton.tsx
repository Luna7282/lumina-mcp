import { useState } from "react";

interface GenerateButtonProps {
  onGenerate: (packageType: string, customInstructions: string) => void;
  isGenerating: boolean;
}

const PACKAGE_TYPES = [
  { id: "quick", label: "Quick", hint: "1 video" },
  { id: "full", label: "Full", hint: "5 videos" },
  { id: "technical", label: "Technical", hint: "3 videos" },
];

export default function GenerateButton({ onGenerate, isGenerating }: GenerateButtonProps) {
  const [open, setOpen] = useState(false);
  const [packageType, setPackageType] = useState("full");
  const [customInstructions, setCustomInstructions] = useState("");

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={isGenerating}
        className="w-full rounded-lg bg-gradient-to-r from-accent to-purple-600 py-3 text-sm font-semibold text-white shadow-lg shadow-accent/20 transition-transform hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isGenerating ? "Generating…" : "Generate Package"}
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-md rounded-xl border border-border bg-surface p-6">
            <h3 className="mb-4 text-lg font-semibold text-text-primary">
              Generate video package
            </h3>

            <p className="mb-2 text-sm text-text-muted">Package type</p>
            <div className="mb-4 grid grid-cols-3 gap-2">
              {PACKAGE_TYPES.map((pt) => (
                <button
                  key={pt.id}
                  type="button"
                  onClick={() => setPackageType(pt.id)}
                  className={`rounded-lg border px-3 py-2 text-center text-sm transition-colors ${
                    packageType === pt.id
                      ? "border-accent bg-accent/10 text-accent"
                      : "border-border text-text-muted hover:text-text-primary"
                  }`}
                >
                  <div className="font-medium">{pt.label}</div>
                  <div className="text-xs opacity-70">{pt.hint}</div>
                </button>
              ))}
            </div>

            <p className="mb-2 text-sm text-text-muted">
              Custom instructions (optional)
            </p>
            <textarea
              value={customInstructions}
              onChange={(e) => setCustomInstructions(e.target.value)}
              rows={3}
              placeholder="e.g. focus on the API layer"
              className="mb-6 w-full resize-none rounded-lg border border-border bg-background p-3 text-sm text-text-primary placeholder:text-text-muted/60 focus:border-accent focus:outline-none"
            />

            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="flex-1 rounded-lg border border-border py-2.5 text-sm font-medium text-text-muted hover:text-text-primary"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  onGenerate(packageType, customInstructions);
                  setOpen(false);
                }}
                className="flex-1 rounded-lg bg-accent py-2.5 text-sm font-semibold text-white hover:bg-accent-hover"
              >
                Generate
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
