import { defineStore } from 'pinia'
import { WhoAmISchema, type WhoAmI } from '~~/shared/schemas/user'

// Reflects Django's auth state for the UI only — all authorization stays
// server-side. Loaded once via useApi('/arch/api/v1/whoami/').
export const useUserStore = defineStore('user', {
  state: (): { loaded: boolean; me: WhoAmI } => ({
    loaded: false,
    me: { authenticated: false, username: '', is_staff: false, is_superuser: false },
  }),
  actions: {
    async load() {
      if (this.loaded) return
      try {
        this.me = await useApi('/arch/api/v1/whoami/', WhoAmISchema)
      } catch {
        // leave defaults (anonymous) on failure
      } finally {
        this.loaded = true
      }
    },
  },
})
