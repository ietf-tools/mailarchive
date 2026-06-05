<script setup lang="ts">
import { ListsResponseSchema } from '~~/shared/schemas/list'

const { data, error } = await useAsyncData('lists-browse', () =>
  useApi('/arch/api/v1/lists/', ListsResponseSchema),
)

const lists = computed(() => data.value?.lists ?? [])
const privateLists = computed(() => lists.value.filter((l) => l.private))
const activeLists = computed(() => lists.value.filter((l) => !l.private && l.active))
const inactiveLists = computed(() => lists.value.filter((l) => !l.private && !l.active))

useHead({ title: 'Browse lists — IETF Mail Archive' })
</script>

<template>
  <div>
    <h1 class="mb-4 text-2xl font-bold text-gray-900">Browse lists</h1>

    <p v-if="error" class="text-red-600">Could not load lists.</p>

    <template v-else>
      <ListSection title="Private" :lists="privateLists" />
      <ListSection title="Active" :lists="activeLists" />
      <ListSection title="Inactive" :lists="inactiveLists" />
      <p v-if="!lists.length" class="text-gray-500">No lists available.</p>
    </template>
  </div>
</template>
