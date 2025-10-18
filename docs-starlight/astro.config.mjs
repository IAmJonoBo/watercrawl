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
        { label: "Home", slug: "index" },
        { label: "Gap Analysis", slug: "gap-analysis" },
        { label: "Architecture", slug: "architecture" },
        { label: "Data Quality & Research", slug: "data-quality" },
        { label: "CLI Guide", slug: "cli" },
        { label: "MCP Integration", slug: "mcp" },
        { label: "Operations", slug: "operations" },
        { label: "Lineage Lakehouse", slug: "lineage-lakehouse" },
      ],
    }),
  ],
});
