// Prebuild staging (story 1.7 D5): copy the committed manifest.json and
// every committed figure export (PNG/SVG + its .figure.json record) into
// the gitignored web/public/artifacts/ so pages bind from the build-time
// tree. This is build plumbing, not a second source: the committed
// exports stay single-sourced under artifacts/ (AD-12), the records ship
// alongside the exports, and the staging copy is wiped with dist.
//
// Fails loudly when the manifest is missing (the pipeline must have run).

import { cpSync, existsSync, mkdirSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(webRoot, "..");

const manifest = path.join(repoRoot, "manifest.json");
if (!existsSync(manifest)) {
  console.error(
    `stage-artifacts: missing ${manifest} — run the pipeline ` +
      "(`uv run python scripts/pipeline.py`) before building the site"
  );
  process.exit(1);
}

const dest = path.join(webRoot, "public", "artifacts");
const figuresDest = path.join(dest, "figures");
mkdirSync(figuresDest, { recursive: true });

cpSync(manifest, path.join(dest, "manifest.json"));

const figuresDir = path.join(repoRoot, "artifacts", "figures");
let figureFiles = 0;
if (existsSync(figuresDir)) {
  for (const name of readdirSync(figuresDir)) {
    if (
      !name.endsWith(".png") &&
      !name.endsWith(".svg") &&
      !name.endsWith(".figure.json")
    ) {
      continue;
    }
    const src = path.join(figuresDir, name);
    if (!statSync(src).isFile()) {
      continue;
    }
    cpSync(src, path.join(figuresDest, name));
    figureFiles += 1;
  }
}

console.log(
  `stage-artifacts: staged manifest.json + ${figureFiles} figure file(s) ` +
    "into web/public/artifacts/"
);
