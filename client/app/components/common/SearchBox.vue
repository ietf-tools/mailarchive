<script setup lang="ts">
const props = withDefaults(defineProps<{ initial?: string; autofocus?: boolean }>(), {
  initial: '',
  autofocus: false,
})

const term = ref(props.initial)

function submit() {
  const q = term.value.trim()
  return navigateTo({ path: '/arch/search/', query: q ? { q } : {} })
}
</script>

<template>
  <form class="flex w-full items-center gap-2" @submit.prevent="submit">
    <div class="relative flex-1">
      <Icon
        name="lucide:search"
        class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
      />
      <input
        v-model="term"
        type="search"
        spellcheck="false"
        :autofocus="autofocus"
        placeholder="Search the mail archive…"
        class="w-full rounded-md border border-gray-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
      />
    </div>
    <button
      type="submit"
      class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
    >
      Search
    </button>
  </form>
</template>
