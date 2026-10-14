// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  devtools: { enabled: true },
  extends: ['@nuxt/ui-pro'],
  modules: [
    '@nuxt/ui',
    '@nuxtjs/color-mode',
    '@nuxt/content',
    'nuxt-icon',
    'nuxt-og-image',
    "@nuxtjs/hanko"
  ],
  colorMode: {
    preference: 'dark',
  },
  css: ['katex/dist/katex.min.css', '~/assets/css/epic-figures.css'],
  content: {
    markdown: {
      // LaTeX math in the docs: $inline$ and $$display$$
      remarkPlugins: ['remark-math'],
      rehypePlugins: { 'rehype-katex': { output: 'html' } }
    }
  },
  hanko: {
    apiURL: process.env.NUXT_PUBLIC_HANKO_API_URL
  },
  ui: {
    icons: ['heroicons', 'simple-icons', 'material-symbols']
  },
  routeRules: {
    // Revalidate the docs search index on every use so a rebuild is picked up immediately
    '/api/search.json': { prerender: true, headers: { 'cache-control': 'no-cache' } },
    '/docs': { redirect: '/docs/introduction', prerender: false },
    '/api/v1/**': { proxy: { to: 'http://127.0.0.1:8000/api/v1/**' } }
  },
  runtimeConfig: {
    // Public keys that are exposed to the client
    public: {
      fastapiBase: process.env.NUXT_FAST_API_BASE || '/api/v1',
      // Canonical origin used for canonical links, Open Graph URLs and the sitemap
      siteUrl: process.env.NUXT_PUBLIC_SITE_URL || 'https://epic-astronomy.org'
    }
  },
  vite: {
    optimizeDeps: {
      include: ["plotly.js-dist-min"],
    },
  },
  experimental: {
    componentIslands: true
  }
})