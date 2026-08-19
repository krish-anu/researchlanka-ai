import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Guards the design system against silent drift.
 *
 * The system is defined once in `globals.css` and documented in the Stitch
 * project's designMd, but nothing stopped a page from reaching for Tailwind's
 * defaults instead — and most of them had. At the point this suite was written
 * the pages carried 91 off-scale type utilities and 20 off-scale radii, which
 * is how a coherent system ends up looking inconsistent without anyone
 * deciding it should.
 *
 * These are source scans rather than render assertions because that is what the
 * failure mode actually is: a class name typed at a call site, not a bug in a
 * component.
 */
const SOURCE_ROOT = join(process.cwd(), "src");

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry) ? [path] : [];
  });
}

const FILES = sourceFiles(SOURCE_ROOT).map((path) => ({
  path: path.slice(SOURCE_ROOT.length + 1).replace(/\\/g, "/"),
  source: readFileSync(path, "utf8"),
}));

/** Matches inside a className string only, so prose is never flagged. */
function offenders(pattern: RegExp): string[] {
  return FILES.flatMap(({ path, source }) => {
    const found = new Set<string>();
    for (const attribute of source.match(/className=(?:"[^"]*"|\{`[^`]*`\})/g) ?? []) {
      for (const hit of attribute.match(pattern) ?? []) found.add(hit);
    }
    return [...found].map((hit) => `${path}: ${hit}`);
  });
}

describe("type scale", () => {
  it("uses only the design system's named sizes", () => {
    // The system defines h1/h2/h3, body-lg/md/sm, mono and label. Tailwind's
    // default scale is a parallel set of sizes that do not line up with it, so
    // mixing the two produces headings a few pixels off from each other.
    expect(offenders(/\btext-(xs|sm|base|lg|xl|[2-9]xl)\b/g)).toEqual([]);
  });
});

describe("shape", () => {
  it("uses the single 4px radius on containers and controls", () => {
    // "A consistent 4px radius is applied to all interactive elements and
    // containers." A circle is still allowed for a dot, checked below.
    expect(offenders(/\brounded-(sm|md|lg|xl|[2-9]xl)\b/g)).toEqual([]);
  });

  it("allows rounded-full only for colour dots, never for pills", () => {
    // A source dot is a dot. A tag is a 4px chip — a pill would be a second
    // shape language competing with the system's one radius.
    const pills = FILES.flatMap(({ path, source }) =>
      (source.match(/className="[^"]*rounded-full[^"]*"/g) ?? [])
        .filter((attribute) => /\bpx-|\bpy-/.test(attribute))
        .map((attribute) => `${path}: ${attribute.slice(0, 70)}`),
    );

    expect(pills).toEqual([]);
  });
});

describe("elevation", () => {
  it("stays flat except for the overlay class", () => {
    // "The design system is strictly flat. Depth is communicated through tonal
    // changes and rules rather than shadows." Overlays are the one exception
    // and carry their shadow in `.overlay`, so no component should declare one.
    expect(offenders(/\bshadow-(?!none)[a-z0-9[\]/(),.-]+/g)).toEqual([]);
  });
});

describe("palette", () => {
  it("uses only semantic tokens, never Tailwind's default colours", () => {
    // Every colour carries meaning here — brand, machine, provenance, status.
    // A raw gray-500 has no meaning and no dark-mode counterpart.
    expect(
      offenders(
        /\b(text|bg|border|fill|stroke|ring)-(gray|slate|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-[0-9]{2,3}\b/g,
      ),
    ).toEqual([]);
  });
});

describe("page titles", () => {
  it("uses the responsive 32/40 pair rather than a single fixed size", () => {
    // `text-h1` is 40px flat, which wraps a short title onto three lines on a
    // 390px phone. `.title-page` carries the h1 / h1-mobile pair.
    const pageFiles = FILES.filter(
      ({ path }) => path.startsWith("app/") && path.endsWith("page.tsx"),
    );
    const fixed = pageFiles
      // Scoped to <h1> elements: `text-h1` is a legitimate size for a large
      // figure, and only a page heading has to shrink on a phone.
      .filter(({ source }) => /<h1[^>]*className="[^"]*\btext-h1\b/.test(source))
      .map(({ path }) => path);

    expect(fixed).toEqual([]);
  });

  it("gives every top-level page exactly one h1", () => {
    const multiple = FILES.filter(
      ({ path, source }) =>
        path.startsWith("app/") &&
        path.endsWith("page.tsx") &&
        (source.match(/<h1\b/g) ?? []).length > 1,
    ).map(({ path }) => path);

    expect(multiple).toEqual([]);
  });
});

describe("globals.css defines what the components rely on", () => {
  const css = readFileSync(join(SOURCE_ROOT, "app", "globals.css"), "utf8");

  it.each(["panel", "sunk", "machine-panel", "data-mono", "label-caps", "scroll-x", "title-page", "overlay", "field", "chip"])(
    "defines .%s",
    (name) => {
      expect(css).toContain(`.${name} {`);
    },
  );

  it("pairs every light-mode colour token with a dark-mode value", () => {
    // A token defined only on :root renders a light colour on a dark surface.
    const dark = css.slice(css.indexOf("@media (prefers-color-scheme: dark)"));
    const root = css.slice(css.indexOf(":root {"), css.indexOf("@media"));

    const names = (block: string) =>
      new Set((block.match(/--[a-z0-9-]+(?=:)/g) ?? []).filter((n) => !n.startsWith("--font")));

    const missing = [...names(root)].filter((token) => !names(dark).has(token));

    expect(missing).toEqual([]);
  });

  it("keeps the responsive half of the page title", () => {
    expect(css).toMatch(/@media \(min-width: 768px\)[\s\S]*\.title-page/);
  });
});
