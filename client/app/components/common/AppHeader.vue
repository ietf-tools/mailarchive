<script setup lang="ts">
const route = useRoute()
const userStore = useUserStore()

// Reflect Django auth state (loaded once, SSR + client).
await useAsyncData('whoami', async () => {
  await userStore.load()
  return userStore.me
})

const loginUrl = computed(() => `/accounts/login/?next=${encodeURIComponent(route.fullPath)}`)
</script>

<template>
  <header class="border-b border-gray-200 bg-white">
    <div class="mx-auto flex w-full max-w-6xl items-center gap-6 px-4 py-3">
      <NuxtLink to="/arch/" class="flex items-center gap-2 font-semibold text-gray-900">
        <Icon name="lucide:mails" class="text-xl text-blue-600" />
        <span>IETF Mail Archive</span>
      </NuxtLink>

      <nav class="flex items-center gap-4 text-sm text-gray-600">
        <NuxtLink to="/arch/" class="hover:text-blue-600">Home</NuxtLink>
        <NuxtLink to="/arch/browse/" class="hover:text-blue-600">Browse</NuxtLink>
        <NuxtLink to="/arch/search/" class="hover:text-blue-600">Search</NuxtLink>
      </nav>

      <div class="ml-auto text-sm">
        <span v-if="userStore.me.authenticated" class="text-gray-600">
          {{ userStore.me.username }}
          <a href="/arch/logout/" class="ml-2 text-blue-600 hover:underline">Sign out</a>
        </span>
        <a v-else :href="loginUrl" class="text-blue-600 hover:underline">Sign in</a>
      </div>
    </div>
  </header>
</template>
