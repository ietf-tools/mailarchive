<script setup lang="ts">
import { ListsResponseSchema } from '~~/shared/schemas/list'

const q = ref('')
const inputEl = ref<HTMLInputElement | null>(null)
const open = ref(false)
const activeIndex = ref(-1)
const menuWidth = ref<number | undefined>(undefined)

// Demo lists power both the placeholder hint and the typeahead.
const { data: listsData } = await useAsyncData('lists-home', () =>
  useApi('/arch/api/v1/lists/', ListsResponseSchema),
)
const names = computed(() => (listsData.value?.lists ?? []).map((l) => l.name))
const demoLists = computed(() => names.value.join(', '))
const placeholder = computed(() =>
  demoLists.value
    ? `Enter list name or search query... (demo uses: ${demoLists.value})`
    : 'Enter list name or search query...',
)

// bootstrap3-typeahead-style matching: case-insensitive substring,
// prefix matches first, capped at 8.
const matches = computed(() => {
  const term = q.value.trim().toLowerCase()
  if (!term) return []
  return names.value
    .filter((n) => n.toLowerCase().includes(term))
    .toSorted((a, b) => {
      const aw = a.toLowerCase().startsWith(term) ? 0 : 1
      const bw = b.toLowerCase().startsWith(term) ? 0 : 1
      return aw - bw || a.localeCompare(b)
    })
    .slice(0, 8)
})

function openMenu() {
  if (matches.value.length) {
    open.value = true
    if (inputEl.value) menuWidth.value = inputEl.value.offsetWidth
  } else {
    open.value = false
  }
}
watch(q, () => {
  activeIndex.value = -1
  openMenu()
})

function escapeHtml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
function highlight(name: string) {
  const term = q.value.trim()
  const i = name.toLowerCase().indexOf(term.toLowerCase())
  if (!term || i < 0) return escapeHtml(name)
  return (
    escapeHtml(name.slice(0, i)) +
    '<strong>' +
    escapeHtml(name.slice(i, i + term.length)) +
    '</strong>' +
    escapeHtml(name.slice(i + term.length))
  )
}

function selectItem(name: string) {
  q.value = name
  open.value = false
  activeIndex.value = -1
  inputEl.value?.focus()
}
function move(delta: number) {
  if (!open.value) {
    openMenu()
    return
  }
  const n = matches.value.length
  if (!n) return
  activeIndex.value = (activeIndex.value + delta + n) % n
}
function onEnter() {
  if (open.value && activeIndex.value >= 0) selectItem(matches.value[activeIndex.value]!)
  else submit()
}

function submit() {
  const term = q.value.trim()
  open.value = false
  if (!term) return navigateTo({ path: '/arch/search/' })
  // Mirror the live site: an exact list name takes you to that list.
  if (names.value.includes(term)) return navigateTo(`/arch/browse/${term}/`)
  return navigateTo({ path: '/arch/search/', query: { q: term } })
}

onMounted(() => inputEl.value?.focus())

useHead({ title: 'IETF Mail List Archives' })
</script>

<template>
  <div class="search-wrapper">
    <div class="search-container">
      <form id="id_search_form" name="search-form" @submit.prevent="submit">
        <div class="position-relative">
          <div class="input-group">
            <input
              id="id_q"
              ref="inputEl"
              v-model="q"
              name="q"
              type="search"
              class="form-control typeahead"
              :placeholder="placeholder"
              spellcheck="false"
              autocomplete="off"
              @focus="openMenu"
              @blur="open = false"
              @keydown.down.prevent="move(1)"
              @keydown.up.prevent="move(-1)"
              @keydown.enter.prevent="onEnter"
              @keydown.esc="open = false"
            />
            <div class="input-group-append">
              <button class="btn btn-secondary" type="submit">
                <span class="fa fa-search" aria-hidden="true"></span>
              </button>
            </div>
          </div>

          <ul
            v-if="open && matches.length"
            class="typeahead dropdown-menu show"
            :style="{ display: 'block', top: '100%', left: '0', width: menuWidth ? `${menuWidth}px` : 'auto' }"
          >
            <li v-for="(m, i) in matches" :key="m" :class="{ active: i === activeIndex }">
              <a
                class="dropdown-item"
                href="#"
                @mousedown.prevent="selectItem(m)"
                @mouseenter="activeIndex = i"
                v-html="highlight(m)"
              ></a>
            </li>
          </ul>
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
