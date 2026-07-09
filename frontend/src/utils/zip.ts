const CODE_EXTENSIONS = new Set([
  ".py",
  ".js",
  ".jsx",
  ".ts",
  ".tsx",
  ".go",
  ".rs",
  ".java",
  ".c",
  ".cpp",
  ".rb",
  ".cs",
  ".kt",
  ".scala",
  ".php",
  ".swift",
  ".lua",
  ".toml",
  ".yaml",
  ".yml",
  ".json",
  ".md",
  ".sh",
]);

// Directories that are never source code: dependency trees, virtualenvs,
// build output, VCS/tooling metadata. A monorepo zip commonly bundles all
// of these, which can blow past the backend's 500-file cap by orders of
// magnitude if left unfiltered.
const IGNORED_DIR_NAMES = new Set([
  "node_modules",
  ".venv",
  "venv",
  "env",
  "__pycache__",
  ".git",
  ".github",
  ".pytest_cache",
  ".mypy_cache",
  ".ruff_cache",
  ".tox",
  "dist",
  "build",
  ".next",
  "out",
  "target",
  "site-packages",
  ".idea",
  ".vscode",
  ".claude",
  "coverage",
  "htmlcov",
  ".cache",
  ".parcel-cache",
  ".turbo",
  "vendor",
  ".pnpm",
  ".yarn",
]);

const MAX_FILES = 500;

function isIgnoredPath(path: string): boolean {
  return path
    .split("/")
    .some((segment) => IGNORED_DIR_NAMES.has(segment) || segment.endsWith(".egg-info"));
}

export async function extractZip(file: File): Promise<Record<string, string>> {
  const JSZip = (await import("jszip")).default;
  const zip = await JSZip.loadAsync(file);
  const files: Record<string, string> = {};

  await Promise.all(
    Object.entries(zip.files).map(async ([path, zipEntry]) => {
      if (zipEntry.dir) return;
      if (isIgnoredPath(path)) return;
      const ext = "." + (path.split(".").pop()?.toLowerCase() ?? "");
      if (!CODE_EXTENSIONS.has(ext)) return;

      try {
        const content = await zipEntry.async("string");
        if (content.length > 100_000) return;
        // Strip top-level folder from path (common in zip files)
        const cleanPath = path.split("/").slice(1).join("/");
        if (cleanPath) files[cleanPath] = content;
      } catch {
        // skip unreadable files
      }
    }),
  );

  const paths = Object.keys(files);
  if (paths.length > MAX_FILES) {
    throw new Error(
      `This project has ${paths.length} analyzable files, which is over Lumina's ${MAX_FILES}-file limit. ` +
        `Try zipping a subpackage or a smaller subdirectory instead of the whole repo.`,
    );
  }

  return files;
}
