import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..", "src");
const EXTENSIONS = new Set([".ts", ".tsx", ".js", ".jsx"]);
const BLOCKED = [
  { pattern: /\bdebugger\b/, label: "debugger statement" },
  { pattern: /\bconsole\.log\s*\(/, label: "console.log" },
];

async function* walk(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      yield* walk(fullPath);
    } else if (EXTENSIONS.has(path.extname(entry.name))) {
      yield fullPath;
    }
  }
}

const findings = [];

for await (const filePath of walk(ROOT)) {
  const text = await readFile(filePath, "utf8");
  const lines = text.split(/\r?\n/);
  lines.forEach((line, index) => {
    for (const blocked of BLOCKED) {
      if (blocked.pattern.test(line)) {
        findings.push(
          `${path.relative(process.cwd(), filePath)}:${index + 1}: ${blocked.label}`,
        );
      }
    }
  });
}

if (findings.length > 0) {
  console.error("Debug-only code found:");
  findings.forEach((finding) => console.error(`  ${finding}`));
  process.exit(1);
}
