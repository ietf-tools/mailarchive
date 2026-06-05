<script setup lang="ts">
import { MessageDetailSchema } from '~~/shared/schemas/message'

const route = useRoute()
const apiPath = computed(() => `/arch/api/v1/msg/${route.params.list}/${route.params.id}/`)

const { data, error } = await useAsyncData(
  'msg-detail',
  () => useApi(apiPath.value, MessageDetailSchema),
  { watch: [apiPath] },
)

useHead({ title: () => `${data.value?.subject || 'Message'} — IETF Mail Archive` })
</script>

<template>
  <div>
    <p v-if="error" class="text-red-600">Message not found, removed, or access denied.</p>

    <article v-else-if="data">
      <DetailNavbar :msg="data" class="mb-3" />
      <MessageHeaders :msg="data" />

      <div class="mb-4 flex flex-wrap gap-4 text-sm">
        <a :href="data.download_url" class="text-blue-600 hover:underline">Download</a>
        <NuxtLink :to="data.date_index_url" class="text-blue-600 hover:underline">Date index</NuxtLink>
        <NuxtLink :to="data.thread_index_url" class="text-blue-600 hover:underline">
          Thread index
        </NuxtLink>
      </div>

      <MessageBody :html="data.body" />

      <section class="mt-6 border-t border-gray-200 pt-4">
        <h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">Thread</h2>
        <ThreadSnippet :html="data.thread_snippet" />
      </section>
    </article>
  </div>
</template>
