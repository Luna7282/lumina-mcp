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

export async function extractZip(file: File): Promise<Record<string, string>> {
  const JSZip = (await import("jszip")).default;
  const zip = await JSZip.loadAsync(file);
  const files: Record<string, string> = {};

  await Promise.all(
    Object.entries(zip.files).map(async ([path, zipEntry]) => {
      if (zipEntry.dir) return;
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

  return files;
}
