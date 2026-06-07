<script setup lang="ts">
import { ListsResponseSchema } from '~~/shared/schemas/list'

const q = ref('')

// Surface which demo lists are loaded, so users know what to search/browse.
const { data: listsData } = await useAsyncData('lists-home', () =>
  useApi('/arch/api/v1/lists/', ListsResponseSchema),
)
const demoLists = computed(() => (listsData.value?.lists ?? []).map((l) => l.name).join(', '))
const placeholder = computed(() =>
  demoLists.value
    ? `Enter list name or search query... (demo uses: ${demoLists.value})`
    : 'Enter list name or search query...',
)

function submit() {
  const term = q.value.trim()
  return navigateTo({ path: '/arch/search/', query: term ? { q: term } : {} })
}

useHead({ title: 'IETF Mail List Archives' })
</script>

<template>
  <div class="search-wrapper">
    <div class="search-container">
      <form id="id_search_form" name="search-form" @submit.prevent="submit">
        <div>
          <div class="input-group">
            <input
              id="id_q"
              v-model="q"
              name="q"
              type="search"
              class="form-control typeahead"
              :placeholder="placeholder"
              spellcheck="false"
            />
            <div class="input-group-append">
              <button class="btn btn-secondary" type="submit">
                <span class="fa fa-search" aria-hidden="true"></span>
              </button>
            </div>
          </div>
        </div>
      </form>
    </div>

    <div class="nav-outer">
      <div class="nav-inner">
        <ul class="navigation">
          <li><a href="https://mailarchive.ietf.org/arch/advsearch/">Advanced Search</a></li>
          <li><NuxtLink to="/arch/browse/">Browse</NuxtLink></li>
        </ul>
      </div>
    </div>
  </div>
</template>
