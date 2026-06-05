<script setup lang="ts">
// The body HTML is produced and sanitized server-side by the Django/MHonArc
// generator (the same HTML the existing detail page renders), so it is a
// trusted string injected with v-html.
defineProps<{ html: string }>()
</script>

<template>
  <div class="message-html" v-html="html" />
</template>
