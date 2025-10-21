// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

// https://astro.build/config
export default defineConfig({
  site: "https://IAmJonoBo.github.io/watercrawl",
  integrations: [
    starlight({
      title: "Watercrawl Documentation",
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/IAmJonoBo/watercrawl",
        },
      ],
      head: [
        {
          tag: "script",
          attrs: {
            type: "module",
            src: "/src/scripts/mermaid-init.js",
          },
        },
      ],
      customCss: ["./src/styles/custom.css"],
      sidebar: [
        { 
          label: "Home", 
          slug: "index" 
        },
        {
          label: "Getting Started",
          items: [
            { label: "Installation & Setup", slug: "guides/getting-started" },
            { label: "Troubleshooting", slug: "guides/troubleshooting" },
          ],
        },
        {
          label: "Tutorials",
          badge: { text: "Learning", variant: "success" },
          items: [
            { label: "First Enrichment", slug: "guides/tutorials/first-enrichment" },
            { label: "Working with Profiles", slug: "guides/tutorials/profiles" },
            { label: "MCP Setup", slug: "guides/tutorials/mcp-setup" },
          ],
        },
        {
          label: "How-To Guides",
          badge: { text: "Problem-Oriented", variant: "tip" },
          items: [
            { label: "CLI Commands", slug: "cli" },
            { label: "MCP Integration", slug: "mcp" },
            { label: "Advanced Configuration", slug: "guides/advanced-configuration" },
          ],
        },
        {
          label: "Reference",
          badge: { text: "Information", variant: "note" },
          items: [
            { label: "API Reference", slug: "reference/api" },
            { label: "Configuration", slug: "reference/configuration" },
            { label: "Data Contracts", slug: "reference/data-contracts" },
          ],
        },
        {
          label: "Explanation",
          badge: { text: "Understanding", variant: "caution" },
          items: [
            { label: "Architecture", slug: "architecture" },
            { label: "Data Quality", slug: "data-quality" },
            { label: "Lineage & Lakehouse", slug: "lineage-lakehouse" },
            { label: "Operations", slug: "operations" },
            { label: "Gap Analysis", slug: "gap-analysis" },
          ],
        },
        {
          label: "Architecture Decisions",
          collapsed: true,
          items: [
            { label: "Overview", slug: "adr/overview" },
            { label: "ADR 0001: Architecture Boundaries", slug: "adr/0001-architecture-boundaries" },
            { label: "ADR 0002: Domain/Application Separation", slug: "adr/0002-domain-application-separation" },
            { label: "ADR 0003: Threat Model & STRIDE/MITRE", slug: "adr/0003-threat-model-stride-mitre" },
          ],
        },
      ],
    }),
  ],
});
