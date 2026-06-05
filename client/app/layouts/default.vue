<template>
  <div class="flex min-h-screen flex-col bg-gray-50 text-gray-900">
    <AppHeader />
    <main class="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
      <slot />
    </main>
    <AppFooter />
  </div>
</template>
