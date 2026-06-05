<script setup lang="ts">
const props = defineProps<{
  page: number
  numPages: number
  hasNext: boolean
  hasPrevious: boolean
}>()
const { update } = useSearchQuery()

function go(n: number) {
  update({ page: n }, { resetPage: false })
}
</script>

<template>
  <div
    v-if="numPages > 1"
    class="flex items-center justify-center gap-3 border-t border-gray-200 p-2 text-sm"
  >
    <button
      :disabled="!hasPrevious"
      class="rounded px-2 py-1 hover:bg-gray-100 disabled:opacity-40"
      @click="go(page - 1)"
    >
      Previous
    </button>
    <span class="text-gray-500">Page {{ page }} of {{ numPages }}</span>
    <button
      :disabled="!hasNext"
      class="rounded px-2 py-1 hover:bg-gray-100 disabled:opacity-40"
      @click="go(page + 1)"
    >
      Next
    </button>
  </div>
</template>
