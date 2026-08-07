/**
 * Checks the categorical chart palette in `src/app/globals.css`.
 *
 * Two properties matter and they are different questions:
 *
 *   1. Separation — can two series be told apart from each other? Measured as
 *      CIEDE2000 between every pair, under normal vision and under simulated
 *      protanopia, deuteranopia and tritanopia (Viénot–Brettel–Mollon 1999
 *      matrices applied in linear RGB).
 *   2. Relief — does a series stand out from the surface it is drawn on?
 *      Measured as WCAG contrast against the page and card backgrounds. A slot
 *      below 3:1 is not banned; it means the chart owes the reader a direct
 *      label or the table view that `TableDisclosure` already provides.
 *
 * Run: node scripts/check-series-contrast.mjs
 * Exits non-zero if any pair falls under the separation floor.
 */

/** ΔE2000 floor for "these read as different series". */
const SEPARATION_FLOOR = 20;

const PALETTES = {
  light: {
    surfaces: { page: "#f3faff", card: "#ffffff" },
    series: { "series-1": "#18818b", "series-2": "#7f5600", "series-3": "#3d0a33" },
  },
  dark: {
    surfaces: { page: "#0e1f26", card: "#16303a" },
    series: { "series-1": "#aceef6", "series-2": "#f5bd63", "series-3": "#d1478c" },
  },
};

/* ------------------------------------------------------------- colour math */

const hexToRgb = (hex) => {
  const n = parseInt(hex.replace("#", ""), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};

const toLinear = (c) => {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
};

const fromLinear = (c) => {
  const v = c <= 0.0031308 ? c * 12.92 : 1.055 * c ** (1 / 2.4) - 0.055;
  return Math.max(0, Math.min(255, Math.round(v * 255)));
};

function relativeLuminance(hex) {
  const [r, g, b] = hexToRgb(hex).map(toLinear);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrastRatio(a, b) {
  const [hi, lo] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/* Viénot–Brettel–Mollon dichromacy matrices, for use on linear RGB. */
const CVD_MATRICES = {
  protanopia: [
    [0.11238, 0.88762, 0.0],
    [0.11238, 0.88762, 0.0],
    [0.00401, -0.00401, 1.0],
  ],
  deuteranopia: [
    [0.29275, 0.70725, 0.0],
    [0.29275, 0.70725, 0.0],
    [-0.02234, 0.02234, 1.0],
  ],
  tritanopia: [
    [1.0, 0.14461, -0.14461],
    [0.0, 1.0, 0.0],
    [0.0, 0.85117, 0.14883],
  ],
};

function simulate(hex, kind) {
  if (kind === "normal") return hex;
  const m = CVD_MATRICES[kind];
  const lin = hexToRgb(hex).map(toLinear);
  const out = m.map((row) => row[0] * lin[0] + row[1] * lin[1] + row[2] * lin[2]);
  return `#${out.map((c) => fromLinear(c).toString(16).padStart(2, "0")).join("")}`;
}

function rgbToLab(hex) {
  const [r, g, b] = hexToRgb(hex).map(toLinear);
  // sRGB -> XYZ (D65), then XYZ -> Lab.
  const x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047;
  const y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  const z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883;
  const f = (t) => (t > 216 / 24389 ? Math.cbrt(t) : (841 / 108) * t + 4 / 29);
  const [fx, fy, fz] = [f(x), f(y), f(z)];
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

/** CIEDE2000. */
function deltaE(hexA, hexB) {
  const [L1, a1, b1] = rgbToLab(hexA);
  const [L2, a2, b2] = rgbToLab(hexB);
  const rad = Math.PI / 180;
  const deg = 180 / Math.PI;

  const C1 = Math.hypot(a1, b1);
  const C2 = Math.hypot(a2, b2);
  const Cbar = (C1 + C2) / 2;
  const G = 0.5 * (1 - Math.sqrt(Cbar ** 7 / (Cbar ** 7 + 25 ** 7)));

  const ap1 = (1 + G) * a1;
  const ap2 = (1 + G) * a2;
  const Cp1 = Math.hypot(ap1, b1);
  const Cp2 = Math.hypot(ap2, b2);

  const hp = (b, ap) => {
    if (b === 0 && ap === 0) return 0;
    const h = Math.atan2(b, ap) * deg;
    return h >= 0 ? h : h + 360;
  };
  const hp1 = hp(b1, ap1);
  const hp2 = hp(b2, ap2);

  const dL = L2 - L1;
  const dC = Cp2 - Cp1;

  let dhp = 0;
  if (Cp1 * Cp2 !== 0) {
    dhp = hp2 - hp1;
    if (dhp > 180) dhp -= 360;
    else if (dhp < -180) dhp += 360;
  }
  const dH = 2 * Math.sqrt(Cp1 * Cp2) * Math.sin((dhp * rad) / 2);

  const Lbar = (L1 + L2) / 2;
  const Cpbar = (Cp1 + Cp2) / 2;

  let hbar = hp1 + hp2;
  if (Cp1 * Cp2 !== 0) {
    if (Math.abs(hp1 - hp2) > 180) hbar += hbar < 360 ? 360 : -360;
    hbar /= 2;
  }

  const T =
    1 -
    0.17 * Math.cos((hbar - 30) * rad) +
    0.24 * Math.cos(2 * hbar * rad) +
    0.32 * Math.cos((3 * hbar + 6) * rad) -
    0.2 * Math.cos((4 * hbar - 63) * rad);

  const Sl = 1 + (0.015 * (Lbar - 50) ** 2) / Math.sqrt(20 + (Lbar - 50) ** 2);
  const Sc = 1 + 0.045 * Cpbar;
  const Sh = 1 + 0.015 * Cpbar * T;
  const Rt =
    -2 *
    Math.sqrt(Cpbar ** 7 / (Cpbar ** 7 + 25 ** 7)) *
    Math.sin(60 * Math.exp(-(((hbar - 275) / 25) ** 2)) * rad);

  return Math.sqrt(
    (dL / Sl) ** 2 +
      (dC / Sc) ** 2 +
      (dH / Sh) ** 2 +
      Rt * (dC / Sc) * (dH / Sh),
  );
}

/* ----------------------------------------------------------------- report */

const VISIONS = ["normal", "protanopia", "deuteranopia", "tritanopia"];
let failures = 0;

for (const [mode, { surfaces, series }] of Object.entries(PALETTES)) {
  console.log(`\n${mode.toUpperCase()}`);

  console.log("  relief (WCAG vs surface)");
  for (const [name, hex] of Object.entries(series)) {
    const parts = Object.entries(surfaces).map(([surfaceName, surfaceHex]) => {
      const ratio = contrastRatio(hex, surfaceHex);
      return `${surfaceName} ${ratio.toFixed(2)}:1${ratio >= 3 ? "" : " (needs labels/table)"}`;
    });
    console.log(`    ${name} ${hex}  ${parts.join("   ")}`);
  }

  console.log(`  separation (ΔE2000, floor ${SEPARATION_FLOOR})`);
  const names = Object.keys(series);
  for (const vision of VISIONS) {
    const results = [];
    for (let i = 0; i < names.length; i += 1) {
      for (let j = i + 1; j < names.length; j += 1) {
        const d = deltaE(
          simulate(series[names[i]], vision),
          simulate(series[names[j]], vision),
        );
        if (d < SEPARATION_FLOOR) failures += 1;
        results.push(
          `${names[i].slice(-1)}v${names[j].slice(-1)} ${d.toFixed(1)}${d < SEPARATION_FLOOR ? " FAIL" : ""}`,
        );
      }
    }
    console.log(`    ${vision.padEnd(13)} ${results.join("   ")}`);
  }
}

console.log(
  failures === 0
    ? "\nAll pairs clear the separation floor under all four vision types."
    : `\n${failures} pair(s) below the ΔE2000 floor of ${SEPARATION_FLOOR}.`,
);
process.exit(failures === 0 ? 0 : 1);
