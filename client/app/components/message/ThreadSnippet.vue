<script setup lang="ts">
// Server-rendered thread snippet HTML (archive/thread_snippet.html), trusted.
defineProps<{ html: string }>()
</script>

<template>
  <div class="thread-snippet text-sm" v-html="html" />
</template>
