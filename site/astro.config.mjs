import { defineConfig } from "astro/config";

// site + base will be adjusted to match the GitHub repo name once the repo
// is created. Defaulting to baritzy.github.io/eytans-newsletter for now.
export default defineConfig({
  site: "https://baritzy.github.io",
  base: "/eytans-newsletter",
  trailingSlash: "ignore",
});