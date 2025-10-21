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
          tag: "link",
          attrs: {
            rel: "stylesheet",
            href: "https://unpkg.com/@primer/css@latest/dist/primer.css",
          },
        },
        {
          tag: "script",
          attrs: {
            type: "module",
          },
          content: `
						import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
						mermaid.initialize({
							startOnLoad: true,
							theme: 'base',
							themeVariables: {
								background: '#ffffff',
								primaryColor: '#f6f8fa',
								primaryTextColor: '#24292f',
								primaryBorderColor: '#d1d9e0',
								lineColor: '#656d76',
								secondaryColor: '#0969da',
								tertiaryColor: '#ffffff',
								textColor: '#24292f',
								mainBkg: '#f6f8fa',
								secondBkg: '#ffffff',
								border1: '#d1d9e0',
								border2: '#d1d9e0',
							},
						});
					`,
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
            { label: "Overview", slug: "adr/index" },
            { label: "ADR 0001: Architecture Boundaries", slug: "adr/0001-architecture-boundaries" },
            { label: "ADR 0002: Domain/Application Separation", slug: "adr/0002-domain-application-separation" },
            { label: "ADR 0003: Threat Model & STRIDE/MITRE", slug: "adr/0003-threat-model-stride-mitre" },
          ],
        },
      ],
    }),
  ],
});
