// Pinned static renderer (story 1.7 D1/D6).
//
// - `base` comes from PAGES_BASE_PATH (default '/'): latest-at-root means
//   the root of the DEPLOYED base; permalinks in later stories must
//   respect it. The deploy workflow maps the repo variable PAGES_BASE_PATH
//   with a '/portfolio-study' fallback.
// - `site` comes from SITE_URL (unset by default).
// - Zero client-side JS (D9): no islands, no hydration; the build emits
//   static HTML that binds values from the staged manifest/records only.
import { defineConfig } from "astro/config";

const base = process.env.PAGES_BASE_PATH || "/";
const site = process.env.SITE_URL || undefined;

export default defineConfig({
  base,
  site,
  output: "static",
});
