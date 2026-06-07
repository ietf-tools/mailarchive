// Where the dev proxy forwards browser /arch/api calls. localhost for a local
// dev server; http://app:8000 inside the compose/devcontainer network.
const devApiTarget = process.env.NUXT_DEV_PROXY_TARGET || 'http://localhost:8000'

// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-06-01',
  devtools: { enabled: true },

  // SSR, like ietf-tools/red — important for archive permalinks + SEO.
  ssr: true,

  modules: ['@pinia/nuxt', 'pinia-plugin-persistedstate/nuxt'],

  // Flat component names (AppHeader, SearchResults, …) regardless of subfolder.
  components: [{ path: '~/components', pathPrefix: false }],

  runtimeConfig: {
    // Server-only: where SSR fetches the Django API directly, forwarding the
    // incoming session cookie. Override with NUXT_API_INTERNAL_BASE.
    apiInternalBase: 'http://localhost:8000',
    public: {
      // Client-side: same-origin. Override with NUXT_PUBLIC_API_BASE.
      apiBase: '',
    },
  },

  // Dev-only: proxy browser API calls to Django so everything is same-origin
  // and the session cookie flows. Only /arch/api/** is proxied.
  $development: {
    nitro: {
      devProxy: {
        '/arch/api': { target: `${devApiTarget}/arch/api`, changeOrigin: true },
      },
    },
  },

  app: {
    head: {
      htmlAttrs: { lang: 'en', 'data-bs-theme': 'auto' },
      title: 'IETF Mail List Archives',
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        { name: 'description', content: 'Search IETF mail list archives' },
      ],
      // The actual stylesheets from mailarchive.ietf.org (copied to public/vendor)
      // so the demo matches the live site exactly.
      link: [
        { rel: 'stylesheet', type: 'text/css', href: '/vendor/fontawesome/css/all.css' },
        { rel: 'stylesheet', type: 'text/css', href: '/vendor/css/bootstrap_custom.css' },
        { rel: 'stylesheet', type: 'text/css', href: '/vendor/css/styles.css' },
      ],
      script: [
        // Sets data-bs-theme based on OS preference (loaded early, like base.html).
        { src: '/vendor/js/bs-theme.js', tagPosition: 'head' },
        // Bootstrap dropdowns / collapse / modal (delegated handlers).
        { src: '/vendor/js/bootstrap.bundle.min.js', tagPosition: 'bodyClose' },
      ],
    },
  },
})
