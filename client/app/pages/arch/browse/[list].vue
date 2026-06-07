<script setup lang="ts">
definePageMeta({ layout: 'results' })
const route = useRoute()
const list = computed(() => String(route.params.list))
useHead({ title: () => list.value })
</script>

<template>
  <SearchResults :browse-list="list" />
</template>
