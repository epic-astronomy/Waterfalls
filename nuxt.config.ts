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
  hanko: {
    apiURL: process.env.NUXT_PUBLIC_HANKO_API_URL
  },
  ui: {
    icons: ['heroicons', 'simple-icons', 'material-symbols']
  },
  routeRules: {
    '/api/search.json': { prerender: true },
    '/docs': { redirect: '/docs/introduction', prerender: false },
    '/api/v1/**': { proxy: { to: 'http://127.0.0.1:8001/api/v1/**' } }
  },
  runtimeConfig: {
    // Public keys that are exposed to the client
    public: {
      fastapiBase: process.env.NUXT_FAST_API_BASE || '/api/v1'
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