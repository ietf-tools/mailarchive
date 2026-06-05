<script setup lang="ts">
import type { EmailList } from '~~/shared/schemas/list'

defineProps<{ title: string; lists: EmailList[] }>()
</script>

<template>
  <section v-if="lists.length" class="mb-6">
    <h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
      {{ title }} <span class="text-gray-400">({{ lists.length }})</span>
    </h2>
    <ul class="grid grid-cols-1 gap-1 sm:grid-cols-2 lg:grid-cols-3">
      <li v-for="l in lists" :key="l.name">
        <NuxtLink
          :to="{ path: '/arch/search/', query: { email_list: l.name } }"
          class="flex items-baseline justify-between rounded px-2 py-1 hover:bg-gray-100"
          :title="l.description"
        >
          <span class="truncate text-blue-600">{{ l.name }}</span>
          <span class="ml-2 shrink-0 text-xs text-gray-400">{{ l.message_count }}</span>
        </NuxtLink>
      </li>
    </ul>
  </section>
</template>
