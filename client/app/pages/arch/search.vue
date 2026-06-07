<script setup lang="ts">
definePageMeta({ layout: 'results' })
const { q } = useSearchQuery()
useHead({ title: () => `${q.value ? `${q.value} ` : ''}IETF Mail List Archives Search Results` })
</script>

<template>
  <SearchResults />
</template>
