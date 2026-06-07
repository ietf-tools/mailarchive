<script setup lang="ts">
import { ListsResponseSchema, type EmailList } from '~~/shared/schemas/list'

definePageMeta({ layout: 'scrolling' })

const { data } = await useAsyncData('lists-browse', () =>
  useApi('/arch/api/v1/lists/', ListsResponseSchema),
)

const lists = computed(() => data.value?.lists ?? [])
const privateLists = computed(() => lists.value.filter((l) => l.private))
const activeLists = computed(() => lists.value.filter((l) => !l.private && l.active))
const inactiveLists = computed(() => lists.value.filter((l) => !l.private && !l.active))

// Mirror get_columns(): split a section into up to 5 columns.
function columns(section: EmailList[]): EmailList[][] {
  if (!section.length) return []
  const size = Math.ceil(section.length / 5)
  const cols: EmailList[][] = []
  for (let i = 0; i < section.length; i += size) cols.push(section.slice(i, i + size))
  return cols
}
function trunc(name: string) {
  return name.length > 19 ? `${name.slice(0, 18)}…` : name
}

const selected = ref('')
function go() {
  if (selected.value) return navigateTo(`/arch/browse/${selected.value}/`)
}

useHead({ title: 'Mail Archive Browse' })
</script>

<template>
  <div class="browse-page container-fluid">
    <div class="row mb-3">
      <div class="offset-md-1 col-md-10 mt-4">
        <form id="id_browse_form" name="browse-form" class="row" @submit.prevent="go">
          <div class="col">
            <select v-model="selected" class="form-select">
              <option value="">(choose list)</option>
              <option v-for="l in lists" :key="l.name" :value="l.name">{{ l.name }}</option>
            </select>
          </div>
          <div class="mb-3 col">
            <button type="submit" class="btn btn-secondary">Go</button>
          </div>
        </form>
      </div>
    </div>

    <div id="private-lists" class="browse-section section">
      <template v-if="privateLists.length">
        <div class="row">
          <div class="offset-md-1 col-md-10"><h3>Private Lists</h3></div>
        </div>
        <div class="row">
          <div
            v-for="(col, ci) in columns(privateLists)"
            :key="`p${ci}`"
            class="browse-column col-md-2"
            :class="{ 'offset-md-1': ci === 0 }"
          >
            <ul class="browse-list">
              <li v-for="l in col" :key="l.name">
                <NuxtLink class="browse-link" :to="`/arch/browse/${l.name}/`">{{ trunc(l.name) }}</NuxtLink>
              </li>
            </ul>
          </div>
        </div>
      </template>
    </div>

    <div id="active-lists" class="browse-section section">
      <div class="row">
        <div class="offset-md-1 col-md-10"><h3>Active Lists</h3></div>
      </div>
      <div class="row">
        <div
          v-for="(col, ci) in columns(activeLists)"
          :key="`a${ci}`"
          class="browse-column col-md-2"
          :class="{ 'offset-md-1': ci === 0 }"
        >
          <ul class="browse-list">
            <li v-for="l in col" :key="l.name">
              <NuxtLink class="browse-link" :to="`/arch/browse/${l.name}/`">{{ trunc(l.name) }}</NuxtLink>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <div id="inactive-lists" class="browse-section section">
      <template v-if="inactiveLists.length">
        <div class="row">
          <div class="offset-md-1 col-md-10"><h3>Inactive Lists</h3></div>
        </div>
        <div class="row">
          <div
            v-for="(col, ci) in columns(inactiveLists)"
            :key="`i${ci}`"
            class="browse-column col-md-2"
            :class="{ 'offset-md-1': ci === 0 }"
          >
            <ul class="browse-list">
              <li v-for="l in col" :key="l.name">
                <NuxtLink class="browse-link" :to="`/arch/browse/${l.name}/`">{{ trunc(l.name) }}</NuxtLink>
              </li>
            </ul>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
