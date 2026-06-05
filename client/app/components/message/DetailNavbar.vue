<script setup lang="ts">
import type { MessageDetail } from '~~/shared/schemas/message'

const props = defineProps<{ msg: MessageDetail }>()

const items = computed(() => [
  { label: '‹ Prev in list', url: props.msg.nav.previous_in_list },
  { label: 'Next in list ›', url: props.msg.nav.next_in_list },
  { label: '‹ Prev in thread', url: props.msg.nav.previous_in_thread },
  { label: 'Next in thread ›', url: props.msg.nav.next_in_thread },
])
</script>

<template>
  <nav class="flex flex-wrap gap-3 text-sm">
    <template v-for="item in items" :key="item.label">
      <NuxtLink v-if="item.url" :to="item.url" class="text-blue-600 hover:underline">
        {{ item.label }}
      </NuxtLink>
      <span v-else class="text-gray-300">{{ item.label }}</span>
    </template>
  </nav>
</template>
