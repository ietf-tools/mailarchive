<script setup lang="ts">
const route = useRoute()
const userStore = useUserStore()

await useAsyncData('whoami', async () => {
  await userStore.load()
  return userStore.me
})

const loginUrl = computed(() => `/accounts/login/?next=${encodeURIComponent(route.fullPath)}`)
</script>

<template>
  <header class="navbar navbar-expand-md navbar-dark fixed-top px-3 py-0">
    <div class="container-fluid">
      <a class="navbar-brand p-0" href="/arch/">
        <img alt="IETF Logo" src="/vendor/images/ietflogo-small-transparent.png" />
        <span class="navbar-text d-none d-md-inline-block">Mail Archive</span>
      </a>
      <button
        class="navbar-toggler"
        type="button"
        data-bs-toggle="collapse"
        data-bs-target="#navbar-main"
        aria-controls="navbar-main"
        aria-expanded="false"
        aria-label="Toggle navigation"
      >
        <span class="navbar-toggler-icon"></span>
      </button>

      <div id="navbar-main" class="navbar-header collapse navbar-collapse">
        <ul class="navbar-nav ms-auto">
          <li class="nav-item d-none d-lg-inline">
            <a class="nav-link" href="https://www.ietf.org/search/">Search www.ietf.org</a>
          </li>
          <li class="nav-item d-none d-lg-inline">
            <a class="nav-link" href="https://datatracker.ietf.org">Search Datatracker</a>
          </li>
          <li class="nav-item d-none d-lg-inline navbar-text pipe"></li>

          <li class="nav-item dropdown">
            <a
              class="nav-link dropdown-toggle"
              href="#"
              id="navbar-help"
              role="button"
              data-bs-toggle="dropdown"
              aria-haspopup="true"
              aria-expanded="false"
              >Help</a
            >
            <div class="dropdown-menu" aria-labelledby="navbar-help">
              <a class="dropdown-item" href="https://mailarchive.ietf.org/arch/help/">Search Syntax</a>
              <a class="dropdown-item" href="https://mailarchive.ietf.org/docs/">API Reference</a>
            </div>
          </li>

          <li v-if="userStore.me.authenticated" class="nav-item dropdown">
            <a
              class="nav-link dropdown-toggle"
              href="#"
              id="navbarUserDropdown"
              data-bs-toggle="dropdown"
              aria-haspopup="true"
              aria-expanded="false"
              >{{ userStore.me.username }}</a
            >
            <ul class="dropdown-menu">
              <li><a class="dropdown-item" href="/arch/logout/">Sign Out</a></li>
            </ul>
          </li>
          <li v-else class="nav-item">
            <a class="nav-link" :href="loginUrl" rel="nofollow">Sign in</a>
          </li>
        </ul>
      </div>
    </div>
  </header>
</template>
