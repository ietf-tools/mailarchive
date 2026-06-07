<script setup lang="ts">
withDefaults(defineProps<{ scrolling?: boolean }>(), { scrolling: false })
</script>

<template>
  <div class="footer bg-body" :class="{ scrolling }">
    <p class="small text-center">
      Nuxt PoC |
      <a href="https://github.com/ietf-tools/mailarch/issues">Report a Bug</a> |
      <a href="mailto:tools-help@ietf.org">By Email</a> |
      <a href="https://status.ietf.org">System Status</a>
    </p>
  </div>
</template>
