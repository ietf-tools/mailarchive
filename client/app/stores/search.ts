import { defineStore } from 'pinia'

// UI/preference state only — the search *query* lives in the URL
// (see useSearchQuery). Mirrors red's useSearchStore with selective persist.
export const useSearchStore = defineStore('search', {
  state: () => ({
    sidebarOpen: true,
    previewOpen: true,
    selectedUrl: '',
  }),
  persist: {
    pick: ['sidebarOpen', 'previewOpen'],
  },
})
