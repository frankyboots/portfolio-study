# web/ — the static Web Study

The pinned Astro 7.x static renderer for the latest Edition. Pages bind
values from the staged `manifest.json` and committed figure records only —
no computation at the render layer, no client-side JavaScript (zero `<script>`
output; no islands, no hydration).

## Environment

- Node 24 (pinned by the root `.nvmrc`).
- Exact `astro` pin in `package.json`; `package-lock.json` committed.
  Use `npm ci`, never `npm install`, in CI.

## Commands (run inside `web/`)

```sh
npm ci          # install the pinned dependencies
npm run build   # stages artifacts, then builds web/dist/
npm run dev     # local dev server (same staging, with hot reload)
```

The `prebuild`/`predev` hook runs `scripts/stage-artifacts.mjs`, which copies
the committed `manifest.json` and every committed figure export
(`artifacts/figures/*.{png,svg,figure.json}`) into the gitignored
`public/artifacts/`. Pages read their data from that staged tree. If the
manifest is missing, staging fails loudly — run the pipeline
(`uv run python scripts/pipeline.py` at the repo root) first.

## Build-time variables

- `PAGES_BASE_PATH` (default `/`): sets Astro's `base`. Latest-at-root means
  the root of the *deployed* base; the deploy workflow maps the repo variable
  `PAGES_BASE_PATH` with a `/portfolio-study` fallback. Internal links and
  public-asset URLs pick up the base automatically.
- `SITE_URL` (default unset): sets Astro's `site`.

## Gitignored build scratch

`node_modules/`, `dist/`, `.astro/`, and `public/artifacts/` are gitignored.
Committed exports stay single-sourced under the root `artifacts/` directory;
the staged copies are build plumbing, wiped with `dist`.

## Editions

Committed frozen edition trees live at `web/editions/{yyyy}[-n]/` (year =
mint date). They start empty until the first mint (`scripts/mint_edition.py`);
the CI no-overwrite guard (`scripts/check_editions.py`, base ref via the
`BASE_REF` env) refuses any modification, deletion, or append under an
edition that exists at the base ref. Creating a new grammar-conforming
edition directory is the only allowed change.

## Deploy

The root `.github/workflows/deploy.yml` builds this tree on push to `main`
and assembles the whole deployed tree: `web/dist` at the base root,
`web/editions/*` under `/editions/`, and the `manual/` placeholder under
`/manual/`. Go-live additionally requires enabling GitHub Pages via
Settings → Pages → GitHub Actions; the workflow ships the pipeline, not the
flip.
