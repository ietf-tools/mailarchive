<script setup lang="ts">
import { ListsResponseSchema } from '~~/shared/schemas/list'

const { data } = await useAsyncData('lists-home', () =>
  useApi('/arch/api/v1/lists/', ListsResponseSchema),
)

const topLists = computed(() =>
  (data.value?.lists ?? []).toSorted((a, b) => b.message_count - a.message_count).slice(0, 12),
)

useHead({ title: 'IETF Mail Archive' })
</script>

<template>
  <div>
    <div class="mx-auto max-w-2xl py-10 text-center">
      <h1 class="text-3xl font-bold text-gray-900">IETF Mail Archive</h1>
      <p class="mt-2 text-gray-500">Search and browse IETF mailing list discussions.</p>
      <div class="mt-6">
        <SearchBox autofocus />
      </div>
      <div class="mt-3 text-sm text-gray-500">
        or
        <NuxtLink to="/arch/browse/" class="text-blue-600 hover:underline">browse all lists</NuxtLink>
      </div>
    </div>

    <section v-if="topLists.length" class="mx-auto max-w-3xl">
      <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
        Most active lists
      </h2>
      <ul class="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        <li v-for="l in topLists" :key="l.name">
          <NuxtLink
            :to="{ path: '/arch/search/', query: { email_list: l.name } }"
            class="flex items-baseline justify-between rounded border border-gray-200 bg-white px-3 py-2 hover:border-blue-300"
          >
            <span class="truncate text-blue-600">{{ l.name }}</span>
            <span class="ml-2 shrink-0 text-xs text-gray-400">{{ l.message_count }}</span>
          </NuxtLink>
        </li>
      </ul>
    </section>
  </div>
</template>
