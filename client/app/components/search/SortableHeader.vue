<script setup lang="ts">
const props = defineProps<{ label: string; field: string }>()
const { sortOrder, update } = useSearchQuery()

const dir = computed(() => {
  if (sortOrder.value === props.field) return 'asc'
  if (sortOrder.value === `-${props.field}`) return 'desc'
  return ''
})

function cycle() {
  update({ so: dir.value === 'asc' ? `-${props.field}` : props.field })
}
</script>

<template>
  <button class="flex items-center gap-1 font-medium hover:text-blue-600" @click="cycle">
    {{ label }}
    <Icon v-if="dir === 'asc'" name="lucide:chevron-up" />
    <Icon v-else-if="dir === 'desc'" name="lucide:chevron-down" />
  </button>
</template>
