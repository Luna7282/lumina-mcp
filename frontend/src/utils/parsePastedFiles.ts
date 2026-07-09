const FILE_MARKER = /^---\s*(.+?)\s*---$/;

export function parsePastedFiles(text: string): Record<string, string> {
  const files: Record<string, string> = {};
  const lines = text.split("\n");

  let currentPath: string | null = null;
  let buffer: string[] = [];

  const flush = () => {
    if (currentPath) {
      files[currentPath] = buffer.join("\n").trim();
    }
    buffer = [];
  };

  for (const line of lines) {
    const match = line.match(FILE_MARKER);
    if (match) {
      flush();
      currentPath = match[1];
    } else if (currentPath) {
      buffer.push(line);
    }
  }
  flush();

  return files;
}
