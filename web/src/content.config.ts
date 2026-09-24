// Minimal content-collection plumbing (AD-12): long-form narrative copy
// lives in web/ content collections; renderers bind it, never compute.
// One placeholder entry until the later story lands real copy.
//
// Astro 7: the config file is src/content.config.ts, the loaders import
// from 'astro/loaders', and schemas are plain zod (v4) via 'astro/zod'.
import { z } from "astro/zod";
import { glob } from "astro/loaders";
import { defineCollection } from "astro:content";

const study = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/study" }),
  schema: z.object({ title: z.string() }),
});

export const collections = { study };
