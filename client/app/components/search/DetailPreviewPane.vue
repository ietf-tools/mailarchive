<script setup lang="ts">
import { MessageDetailSchema } from '~~/shared/schemas/message'
import { msgPermalinkToApi } from '~/utilities/url'

const props = defineProps<{ url: string }>()

const { data, status, error } = await useAsyncData(
  'msg-preview',
  () => (props.url ? useApi(msgPermalinkToApi(props.url), MessageDetailSchema) : Promise.resolve(null)),
  { watch: [() => props.url] },
)
</script>

<template>
  <div class="h-full overflow-y-auto p-4">
    <p v-if="!url" class="text-gray-400">Select a message to preview.</p>
    <p v-else-if="status === 'pending'" class="text-gray-400">Loading…</p>
    <p v-else-if="error" class="text-red-600">Could not load message.</p>
    <article v-else-if="data">
      <MessageHeaders :msg="data" />
      <NuxtLink :to="data.url" class="mb-3 inline-block text-sm text-blue-600 hover:underline">
        Open full message →
      </NuxtLink>
      <MessageBody :html="data.body" />
    </article>
  </div>
</template>
