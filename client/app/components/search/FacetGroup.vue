<script setup lang="ts">
import type { FacetBucket } from '~~/shared/schemas/search'

const props = defineProps<{ title: string; buckets: FacetBucket[]; selected: string[] }>()
const emit = defineEmits<{ (e: 'toggle', key: string): void }>()

const FILTER_CUTOFF = 6
const expanded = ref(false)
const visible = computed(() =>
  expanded.value ? props.buckets : props.buckets.slice(0, FILTER_CUTOFF),
)
</script>

<template>
  <div v-if="buckets.length" class="mb-4">
    <h3 class="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">{{ title }}</h3>
    <ul class="space-y-0.5">
      <li v-for="b in visible" :key="b.key">
        <label class="flex cursor-pointer items-center gap-2 text-sm">
          <input
            type="checkbox"
            :checked="selected.includes(b.key)"
            @change="emit('toggle', b.key)"
          />
          <span class="flex-1 truncate" :title="b.key">{{ b.key }}</span>
          <span class="text-xs text-gray-400">{{ b.doc_count }}</span>
        </label>
      </li>
    </ul>
    <button
      v-if="buckets.length > FILTER_CUTOFF"
      class="mt-1 text-xs text-blue-600 hover:underline"
      @click="expanded = !expanded"
    >
      {{ expanded ? 'less' : `more (${buckets.length - FILTER_CUTOFF})` }}
    </button>
  </div>
</template>
