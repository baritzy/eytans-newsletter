import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

const posts = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "../posts" }),
  schema: z.object({
    date: z.coerce.date(),
    channel: z.string(),
    original_title: z.string(),
    hebrew_title: z.string(),
    category: z.string(),
    video_id: z.string(),
    video_url: z.string().url(),
    duration_sec: z.number().default(0),
    transcript_source: z.string().default("manual"),
    was_truncated: z.boolean().default(false),
    cost_usd: z.number().default(0),
    status: z.string().default("ok"),
    key_points: z.array(z.string()).optional(),
  }),
});

export const collections = { posts };