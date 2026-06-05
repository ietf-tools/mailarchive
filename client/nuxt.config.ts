import tailwindcss from '@tailwindcss/vite'

// Where the dev proxy forwards browser /arch/api calls. localhost for a local
// dev server; http://app:8000 inside the compose/devcontainer network.
const devApiTarget = process.env.NUXT_DEV_PROXY_TARGET || 'http://localhost:8000'

// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-06-01',
  devtools: { enabled: true },

  // SSR, like ietf-tools/red — important for archive permalinks + SEO.
  ssr: true,

  modules: ['@nuxt/icon', '@pinia/nuxt', 'pinia-plugin-persistedstate/nuxt'],

  // Flat component names (AppHeader, ResultsTable, …) regardless of subfolder.
  components: [{ path: '~/components', pathPrefix: false }],

  css: ['~/assets/css/main.css'],

  vite: {
    plugins: [tailwindcss()],
  },

  runtimeConfig: {
    // Server-only: where SSR fetches the Django API directly, forwarding the
    // incoming session cookie. Override with NUXT_API_INTERNAL_BASE.
    apiInternalBase: 'http://localhost:8000',
    public: {
      // Client-side: same-origin. In dev the devProxy below forwards
      // /arch/api/** to Django; in prod nginx does. Override with
      // NUXT_PUBLIC_API_BASE.
      apiBase: '',
    },
  },

  // Dev-only: proxy browser API calls to Django so everything is same-origin
  // and the session cookie flows. Page routes under /arch are served by Nuxt;
  // only /arch/api/** is proxied.
  $development: {
    nitro: {
      devProxy: {
        '/arch/api': {
          target: `${devApiTarget}/arch/api`,
          changeOrigin: true,
        },
      },
    },
  },

  icon: {
    mode: 'svg',
  },

  app: {
    head: {
      title: 'IETF Mail Archive',
      htmlAttrs: { lang: 'en' },
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      ],
    },
  },
})
