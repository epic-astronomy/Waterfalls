// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2026-10-01',
  devtools: { enabled: true },
  modules: [
    '@nuxt/ui',
    '@nuxt/content',
    '@nuxtjs/hanko'
  ],
  ui: {
    theme: {
      // notice: the orange of the skymon review and watch states
      colors: ['primary', 'secondary', 'success', 'info', 'warning', 'error', 'notice']
    }
  },
  colorMode: {
    preference: 'dark'
  },
  css: ['~/assets/css/main.css', 'katex/dist/katex.min.css', '~/assets/css/epic-figures.css'],
  content: {
    // Node's own SQLite (22.13 and later), so no native module is built
    experimental: { sqliteConnector: 'native' },
    build: {
      markdown: {
        // LaTeX math in the docs: $inline$ and $$display$$
        remarkPlugins: { 'remark-math': {} },
        rehypePlugins: { 'rehype-katex': { output: 'html' } }
      }
    }
  },
  // set at run time by NUXT_PUBLIC_HANKO_API_URL
  hanko: {
    apiURL: ''
  },
  icon: {
    // the icon sets are bundled with the server, so no icon is fetched from the Iconify API
    serverBundle: { collections: ['heroicons', 'simple-icons', 'material-symbols', 'lucide'] }
  },
  routeRules: {
    '/docs': { redirect: '/docs/introduction', prerender: false }
  },
  runtimeConfig: {
    // the FastAPI backend that /api/v1 is passed to (NUXT_API_ORIGIN)
    apiOrigin: 'http://127.0.0.1:8000',
    // Public keys that are exposed to the client
    public: {
      fastapiBase: '/api/v1',
      // Canonical origin used for canonical links, Open Graph URLs and the sitemap
      siteUrl: 'https://epic-astronomy.org'
    }
  },
  vite: {
    optimizeDeps: {
      include: ['plotly.js-dist-min']
    }
  },
  experimental: {
    componentIslands: true
  }
})
