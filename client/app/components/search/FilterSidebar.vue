<script setup lang="ts">
import type { Aggregations } from '~~/shared/schemas/search'

defineProps<{ aggregations: Aggregations }>()

const { qdr, listFilters, fromFilters, update, toggleFilter } = useSearchQuery()

const TIME_CHOICES: [string, string][] = [
  ['a', 'Any time'],
  ['d', 'Past 24 hours'],
  ['w', 'Past week'],
  ['m', 'Past month'],
  ['y', 'Past year'],
]
</script>

<template>
  <aside class="w-60 shrink-0 overflow-y-auto border-r border-gray-200 p-3">
    <div class="mb-4">
      <h3 class="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">Time</h3>
      <ul class="space-y-0.5">
        <li v-for="[val, label] in TIME_CHOICES" :key="val">
          <label class="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="radio"
              name="qdr"
              :value="val"
              :checked="qdr === val"
              @change="update({ qdr: val === 'a' ? undefined : val })"
            />
            {{ label }}
          </label>
        </li>
      </ul>
    </div>

    <FacetGroup
      title="List"
      :buckets="aggregations.list_terms ?? []"
      :selected="listFilters"
      @toggle="(k) => toggleFilter('f_list', k)"
    />
    <FacetGroup
      title="From"
      :buckets="aggregations.from_terms ?? []"
      :selected="fromFilters"
      @toggle="(k) => toggleFilter('f_from', k)"
    />
  </aside>
</template>
