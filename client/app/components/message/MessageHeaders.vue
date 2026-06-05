<script setup lang="ts">
import type { MessageDetail } from '~~/shared/schemas/message'
import { formatDate } from '~/utilities/strings'

defineProps<{ msg: MessageDetail }>()
</script>

<template>
  <header class="mb-3 border-b border-gray-200 pb-3">
    <h1 class="text-lg font-semibold text-gray-900">{{ msg.subject || '(no subject)' }}</h1>
    <dl class="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-sm text-gray-600">
      <dt class="font-medium text-gray-500">From</dt>
      <dd class="truncate">{{ msg.frm }}</dd>
      <dt class="font-medium text-gray-500">Date</dt>
      <dd>{{ formatDate(msg.date) }}</dd>
      <dt class="font-medium text-gray-500">List</dt>
      <dd>{{ msg.email_list }}</dd>
      <template v-if="msg.to">
        <dt class="font-medium text-gray-500">To</dt>
        <dd class="truncate">{{ msg.to }}</dd>
      </template>
    </dl>
  </header>
</template>
