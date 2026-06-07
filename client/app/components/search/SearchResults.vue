<script setup lang="ts">
import { SearchResponseSchema, type SearchHit } from '~~/shared/schemas/search'
import { MessageDetailSchema } from '~~/shared/schemas/message'
import { msgPermalinkToApi } from '~/utilities/url'

const props = defineProps<{ browseList?: string }>()

const route = useRoute()
const { q, qdr, listFilters, fromFilters, groupByThread, sortOrder, page, update, toggleFilter } =
  useSearchQuery()

// API path mirrors the page query params, plus email_list in browse mode.
const apiPath = computed(() => {
  const usp = new URLSearchParams()
  for (const [k, v] of Object.entries(route.query)) {
    if (Array.isArray(v)) v.forEach((x) => x != null && usp.append(k, String(x)))
    else if (v != null) usp.append(k, String(v))
  }
  if (props.browseList) usp.set('email_list', props.browseList)
  const qs = usp.toString()
  return '/arch/api/v1/search/' + (qs ? `?${qs}` : '')
})

const { data, status } = await useAsyncData(
  'results',
  () => useApi(apiPath.value, SearchResponseSchema),
  { watch: [apiPath] },
)

const results = computed(() => data.value?.results ?? [])
const aggregations = computed(() => data.value?.aggregations ?? {})
const count = computed(() => data.value?.count ?? 0)
const numPages = computed(() => data.value?.num_pages ?? 1)
const hasNext = computed(() => data.value?.has_next ?? false)
const hasPrevious = computed(() => data.value?.has_previous ?? false)
const gbt = computed(() => groupByThread.value)

// --- UI state ---
const filtersOpen = ref(true)
const previewOpen = ref(false)
const selectedUrl = ref('')
const previewHtml = ref('')
const previewLoading = ref(false)
const expandedList = ref(false)
const expandedFrom = ref(false)

const listBuckets = computed(() => aggregations.value.list_terms ?? [])
const fromBuckets = computed(() => aggregations.value.from_terms ?? [])
const visibleList = computed(() =>
  expandedList.value ? listBuckets.value : listBuckets.value.slice(0, 6),
)
const visibleFrom = computed(() =>
  expandedFrom.value ? fromBuckets.value : fromBuckets.value.slice(0, 6),
)

// --- search box ---
const qInput = ref(q.value)
watch(q, (v) => (qInput.value = v))
function submitSearch() {
  update({ q: qInput.value.trim() || undefined })
}

// --- sorting ---
function sortBy(field: string) {
  update({ so: sortOrder.value === field ? `-${field}` : field })
}
function sortIcon(field: string) {
  if (sortOrder.value === field) return 'fa-sort-asc'
  if (sortOrder.value === `-${field}`) return 'fa-sort-desc'
  return 'fa-sort'
}

// --- time filter ---
function setQdr(val: string) {
  update({ qdr: val || undefined })
}
function qdrActive(val: string) {
  return val ? qdr.value === val : !qdr.value || qdr.value === 'a'
}

// --- pagination ---
function goPage(n: number) {
  update({ page: n }, { resetPage: false })
}

// --- preview ---
async function openPreview(hit: SearchHit) {
  selectedUrl.value = hit.url
  previewOpen.value = true
  previewLoading.value = true
  try {
    const detail = await useApi(msgPermalinkToApi(hit.url), MessageDetailSchema)
    previewHtml.value = detail.body
  } catch {
    previewHtml.value = '<p class="text-danger">Could not load message.</p>'
  } finally {
    previewLoading.value = false
  }
}
function togglePreview() {
  previewOpen.value = !previewOpen.value
}

function listDate(iso: string) {
  return (iso || '').slice(0, 10)
}
function depthClass(depth: number) {
  return `depth-${Math.min(Math.max(depth, 0), 6)}`
}
function frmTrunc(name: string) {
  return name.length > 35 ? `${name.slice(0, 34)}…` : name
}
function fromTrunc(name: string, n: number) {
  return name.length > n ? `${name.slice(0, n - 1)}…` : name
}
</script>

<template>
  <div id="msg-container">
    <div id="sidebar" v-show="filtersOpen">
      <div id="search-filters">
        <template v-if="browseList">
          <p class="text-center">
            Viewing List:<br /><span class="browse-list-name"><b>{{ browseList }}</b></span>
          </p>
          <hr />
        </template>

        <h5 class="mt-4">FILTER BY TIME</h5>
        <ul class="filter-options" tabindex="-1">
          <li class="filter-item"><a :class="{ selected: qdrActive('') }" href="#" @click.prevent="setQdr('')">Anytime</a></li>
          <li class="filter-item"><a :class="{ selected: qdrActive('d') }" href="#" @click.prevent="setQdr('d')">Past day</a></li>
          <li class="filter-item"><a :class="{ selected: qdrActive('w') }" href="#" @click.prevent="setQdr('w')">Past week</a></li>
          <li class="filter-item"><a :class="{ selected: qdrActive('m') }" href="#" @click.prevent="setQdr('m')">Past month</a></li>
          <li class="filter-item"><a :class="{ selected: qdrActive('y') }" href="#" @click.prevent="setQdr('y')">Past year</a></li>
        </ul>

        <div id="filter-box">
          <template v-if="!browseList">
            <h5 class="mt-4">FILTER BY LIST</h5>
            <div id="list-filter" class="filter" tabindex="-1">
              <ul class="filter-options" tabindex="-1">
                <li v-for="(list, i) in visibleList" :key="list.key" class="filter-option form-check">
                  <input
                    class="form-check-input list-facet facetchk"
                    type="checkbox"
                    :id="`id_f_list_${i}`"
                    name="f_list"
                    :value="list.key"
                    :checked="listFilters.includes(list.key)"
                    @change="toggleFilter('f_list', list.key)"
                  />
                  <label class="form-check-label" :for="`id_f_list_${i}`">{{ list.key }} ({{ list.doc_count }})</label>
                </li>
                <li v-if="listBuckets.length > 6" class="control">
                  <a class="more-link" href="#" @click.prevent="expandedList = !expandedList">{{ expandedList ? 'less...' : 'more...' }}</a>
                </li>
              </ul>
            </div>
          </template>

          <h5 class="mt-4">FILTER BY FROM</h5>
          <div id="from-filter" class="filter" tabindex="-1">
            <ul class="filter-options" tabindex="-1">
              <li v-for="(name, i) in visibleFrom" :key="name.key" class="filter-option form-check">
                <input
                  class="form-check-input from-facet facetchk"
                  type="checkbox"
                  :id="`id_f_from_${i}`"
                  name="f_from"
                  :value="name.key"
                  :checked="fromFilters.includes(name.key)"
                  @change="toggleFilter('f_from', name.key)"
                />
                <label class="form-check-label" :for="`id_f_from_${i}`">{{ fromTrunc(name.key, 24) }}</label> ({{ name.doc_count }})
              </li>
              <li v-if="fromBuckets.length > 6" class="control">
                <a class="more-link" href="#" @click.prevent="expandedFrom = !expandedFrom">{{ expandedFrom ? 'less...' : 'more...' }}</a>
              </li>
            </ul>
          </div>
        </div>
      </div>

      <AppFooter />
    </div>

    <div id="msg-components" :class="{ 'x-full-width': !filtersOpen }">
      <nav id="toolbar-left" class="navbar navbar-light bg-body-tertiary rounded shadow-sm float-start toolbar">
        <ul class="navbar-nav me-auto">
          <li id="toggle-filters" class="nav-item">
            <a href="#" class="nav-link" @click.prevent="filtersOpen = !filtersOpen">
              <i class="fa toggle-pane" :class="filtersOpen ? 'fa-chevron-left' : 'fa-chevron-right'" aria-hidden="true"></i>
            </a>
          </li>
        </ul>
      </nav>

      <nav id="toolbar" class="navbar navbar-expand-md navbar-light bg-body-tertiary rounded shadow-sm toolbar">
        <div class="container-fluid">
          <div class="collapse navbar-collapse justify-content-stretch show">
            <ul class="navbar-nav mx-2 flex-shrink-0">
              <li class="nav-item">
                <NuxtLink id="modify-search" class="nav-link" :to="browseList ? '/arch/browse/' : '/arch/'" title="Modify Search">
                  <span v-if="browseList" class="fa fa-arrow-left" aria-hidden="true"></span>
                  <template v-else>Modify Search</template>
                </NuxtLink>
              </li>
              <template v-if="browseList">
                <li class="nav-item"><a class="nav-link" :class="{ active: !gbt }" href="#" @click.prevent="update({ gbt: undefined })">Date</a></li>
                <li class="nav-item"><a id="gbt-link" class="nav-link" :class="{ active: gbt }" href="#" @click.prevent="update({ gbt: '1' })">Thread</a></li>
              </template>
            </ul>

            <form name="search-form" class="ms-3 my-auto flex-grow-1" @submit.prevent="submitSearch">
              <div class="input-group input-group-sm w-100">
                <input
                  v-model="qInput"
                  type="search"
                  name="q"
                  spellcheck="false"
                  :placeholder="browseList ? `Search ${browseList}` : ''"
                  class="form-control"
                  id="id_q"
                />
                <div class="input-group-append">
                  <button class="btn btn-secondary" type="submit"><span class="fa fa-search" aria-hidden="true"></span></button>
                </div>
              </div>
            </form>

            <ul class="navbar-nav">
              <li class="nav-item"><a class="nav-link" href="#" data-bs-toggle="modal" data-bs-target="#export-modal">Export</a></li>
            </ul>
          </div>
        </div>
      </nav>

      <div id="msg-panes" :class="{ 'has-preview': previewOpen }">
        <div id="list-pane">
          <template v-if="gbt">
            <div class="header"><span>Subject</span></div><div class="header"><span>From</span></div><div class="header"><span>Date</span></div><div class="header" :class="{ 'd-none': browseList }"><span>List</span></div>
          </template>
          <template v-else>
            <div class="header sortable"><a class="unsorted sortbutton" href="#" @click.prevent="sortBy('subject')">Subject<i class="fa" :class="sortIcon('subject')" aria-hidden="true"></i></a></div><div class="header sortable"><a class="unsorted sortbutton" href="#" @click.prevent="sortBy('frm')">From<i class="fa" :class="sortIcon('frm')" aria-hidden="true"></i></a></div><div class="header sortable"><a class="unsorted sortbutton" href="#" @click.prevent="sortBy('date')">Date<i class="fa" :class="sortIcon('date')" aria-hidden="true"></i></a></div><div class="header sortable" :class="{ 'd-none': browseList }"><a class="unsorted sortbutton" href="#" @click.prevent="sortBy('email_list')">List<i class="fa" :class="sortIcon('email_list')" aria-hidden="true"></i></a></div>
          </template>

          <div id="msg-list" class="msg-list wrapper" :class="{ 'no-preview': !previewOpen }" tabindex="-1">
            <div class="table msg-table xtable" :class="{ 'thread-sorted': gbt }">
              <div class="xtbody">
                <template v-if="results.length">
                  <div
                    v-for="hit in results"
                    :key="hit.url"
                    class="xtr"
                    :class="{ 'row-selected': hit.url === selectedUrl }"
                  >
                    <div class="xtd subj-col" :class="depthClass(hit.thread_depth)">
                      <span>{{ hit.subject }}</span><a class="msg-detail" :href="hit.url" @click.prevent="openPreview(hit)">{{ hit.subject }}</a>
                    </div>
                    <div class="xtd from-col">{{ frmTrunc(hit.frm_name) }}</div>
                    <div class="xtd date-col">{{ listDate(hit.date) }}</div>
                    <div class="xtd list-col" :class="{ 'd-none': browseList }">{{ hit.email_list }}</div>
                  </div>
                </template>
                <div v-else class="xtr"><div class="xtd no-results">No results found</div></div>
              </div>
            </div>
          </div>

          <div id="msg-list-controls">
            <div id="message-count" class="list-control">{{ count }} Messages</div>
            <div class="list-control page-nav">
              <a v-if="hasPrevious" class="float-start" href="#" @click.prevent="goPage(page - 1)">Previous</a>
              <span class="current-page">Page {{ page }} of {{ numPages }}</span>
              <a v-if="hasNext" class="float-end" href="#" @click.prevent="goPage(page + 1)">Next</a>
            </div>
            <div id="toggle-preview"><a href="#" @click.prevent="togglePreview"><i class="fa toggle-pane" :class="previewOpen ? 'fa-chevron-up' : 'fa-chevron-down'" aria-hidden="true"></i></a></div>
          </div>
        </div>

        <div id="splitter-pane" class="draggable" :class="{ 'js-off': !previewOpen }"></div>

        <div class="view-pane" :class="{ 'js-off': !previewOpen }">
          <p v-if="previewLoading" class="text-secondary">Loading…</p>
          <div v-else v-html="previewHtml"></div>
        </div>
      </div>
    </div>

    <!-- Export modal -->
    <div class="modal fade" id="export-modal" tabindex="-1" role="dialog" aria-hidden="true">
      <div class="modal-dialog" role="document">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Archive Export</h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
          </div>
          <div class="modal-body">
            <div class="export-text"><p>You must be logged in to export messages.</p></div>
          </div>
          <div class="modal-footer">
            <a class="btn btn-secondary disabled" href="#">Mbox</a>
            <a class="btn btn-secondary disabled" href="#">Maildir</a>
            <a class="btn btn-secondary disabled" href="#">URLs</a>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<!-- Global (un-scoped) tweak: lay out the preview pane cleanly without the
     original mailarch.js splitter resizing. -->
<style>
#msg-panes.has-preview #list-pane {
  height: 45%;
}
#msg-panes.has-preview #splitter-pane {
  top: 45%;
}
#msg-panes.has-preview .view-pane {
  top: calc(45% + 8px);
  background-color: var(--bs-body-bg);
}
</style>
