<script setup lang="ts">
import { SplitterGroup, SplitterPanel, SplitterResizeHandle } from 'reka-ui'
import { SearchResponseSchema } from '~~/shared/schemas/search'

definePageMeta({ layout: 'search' })

const { q, apiPath, groupByThread, update } = useSearchQuery()
const store = useSearchStore()

const { data, status, error } = await useAsyncData(
  'search',
  () => useApi(apiPath.value, SearchResponseSchema),
  { watch: [apiPath] },
)

function onSelect(url: string) {
  store.selectedUrl = url
}

useHead({
  title: () => `${q.value ? `${q.value} — ` : ''}Search — IETF Mail Archive`,
})
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- toolbar -->
    <div class="flex items-center gap-4 border-b border-gray-200 px-4 py-2">
      <div class="w-96"><SearchBox :initial="q" /></div>
      <div class="text-sm text-gray-500">
        <span v-if="status === 'pending'">Searching…</span>
        <span v-else-if="data">{{ data.count }} results</span>
      </div>
      <div class="ml-auto flex items-center gap-1 text-sm">
        <button
          class="rounded px-2 py-1"
          :class="!groupByThread ? 'bg-blue-100 text-blue-700' : 'text-gray-500'"
          @click="update({ gbt: undefined })"
        >
          Date
        </button>
        <button
          class="rounded px-2 py-1"
          :class="groupByThread ? 'bg-blue-100 text-blue-700' : 'text-gray-500'"
          @click="update({ gbt: true })"
        >
          Thread
        </button>
      </div>
    </div>

    <p v-if="error" class="p-4 text-red-600">Search error — check the query expression.</p>

    <!-- sidebar + (results | preview) -->
    <div v-else class="flex min-h-0 flex-1">
      <FilterSidebar v-if="data" :aggregations="data.aggregations" />

      <SplitterGroup direction="horizontal" class="min-h-0 flex-1">
        <SplitterPanel :default-size="60" class="flex min-h-0 flex-col">
          <ResultsTable
            :results="data?.results ?? []"
            :selected-url="store.selectedUrl"
            @select="onSelect"
          />
          <Paginator
            v-if="data"
            :page="data.page"
            :num-pages="data.num_pages"
            :has-next="data.has_next"
            :has-previous="data.has_previous"
          />
        </SplitterPanel>

        <SplitterResizeHandle class="w-1 bg-gray-200 hover:bg-blue-300" />

        <SplitterPanel :default-size="40" class="min-h-0 border-l border-gray-200">
          <DetailPreviewPane :url="store.selectedUrl" />
        </SplitterPanel>
      </SplitterGroup>
    </div>
  </div>
</template>
