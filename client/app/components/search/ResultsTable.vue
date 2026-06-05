<script setup lang="ts">
import type { SearchHit } from '~~/shared/schemas/search'
import { formatDate } from '~/utilities/strings'

defineProps<{ results: SearchHit[]; selectedUrl: string }>()
const emit = defineEmits<{ (e: 'select', url: string): void }>()
</script>

<template>
  <div class="min-h-0 flex-1 overflow-y-auto">
    <table class="w-full table-fixed border-collapse text-sm">
      <thead class="sticky top-0 bg-gray-100 text-left text-gray-600">
        <tr>
          <th class="w-1/2 px-3 py-2"><SortableHeader label="Subject" field="subject" /></th>
          <th class="w-1/5 px-3 py-2"><SortableHeader label="From" field="frm" /></th>
          <th class="w-[15%] px-3 py-2"><SortableHeader label="Date" field="date" /></th>
          <th class="w-[15%] px-3 py-2"><SortableHeader label="List" field="email_list" /></th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="hit in results"
          :key="hit.url"
          class="cursor-pointer border-t border-gray-100 hover:bg-blue-50"
          :class="{ 'bg-blue-100': hit.url === selectedUrl }"
          @click="emit('select', hit.url)"
        >
          <td
            class="truncate px-3 py-1.5"
            :style="{ paddingLeft: `${0.75 + hit.thread_depth}rem` }"
          >
            {{ hit.subject || '(no subject)' }}
          </td>
          <td class="truncate px-3 py-1.5">{{ hit.frm_name }}</td>
          <td class="truncate px-3 py-1.5 text-gray-500">{{ formatDate(hit.date) }}</td>
          <td class="truncate px-3 py-1.5 text-gray-500">{{ hit.email_list }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="!results.length" class="p-4 text-gray-500">No messages found.</p>
  </div>
</template>
