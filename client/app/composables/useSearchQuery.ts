import type { LocationQueryRaw } from 'vue-router'

function str(v: unknown): string {
  if (Array.isArray(v)) return String(v[0] ?? '')
  return v == null ? '' : String(v)
}

function csv(v: unknown): string[] {
  const s = str(v)
  return s ? s.split(',').filter(Boolean) : []
}

/**
 * The URL query string is the single source of truth for search state
 * (mirroring red's search page). Reads are computed off the route; writes go
 * through `navigateTo(..., { replace: true })`, which re-runs the page's
 * `useAsyncData` keyed on the full path.
 */
export function useSearchQuery() {
  const route = useRoute()

  const q = computed(() => str(route.query.q))
  const emailList = computed(() => str(route.query.email_list))
  const page = computed(() => Number(route.query.page) || 1)
  const groupByThread = computed(() => route.query.gbt === '1')
  const sortOrder = computed(() => str(route.query.so))
  const qdr = computed(() => str(route.query.qdr) || 'a')
  const listFilters = computed(() => csv(route.query.f_list))
  const fromFilters = computed(() => csv(route.query.f_from))

  // API path mirrors the page's query params exactly.
  const apiPath = computed(() => {
    const usp = new URLSearchParams()
    for (const [k, v] of Object.entries(route.query)) {
      if (Array.isArray(v)) v.forEach((x) => x != null && usp.append(k, String(x)))
      else if (v != null) usp.append(k, String(v))
    }
    const qs = usp.toString()
    return '/arch/api/v1/search/' + (qs ? `?${qs}` : '')
  })

  function update(
    params: Record<string, string | number | boolean | undefined | null>,
    opts: { resetPage?: boolean } = {},
  ) {
    const { resetPage = true } = opts
    const query: Record<string, string> = {}
    for (const [k, v] of Object.entries(route.query)) {
      query[k] = str(v)
    }
    if (resetPage) delete query.page
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === null || v === '' || v === false) delete query[k]
      else query[k] = String(v)
    }
    return navigateTo({ path: route.path, query: query as LocationQueryRaw }, { replace: true })
  }

  function toggleFilter(key: 'f_list' | 'f_from', value: string) {
    const current = csv(route.query[key])
    const next = current.includes(value)
      ? current.filter((v) => v !== value)
      : [...current, value]
    return update({ [key]: next.join(',') })
  }

  return {
    q,
    emailList,
    page,
    groupByThread,
    sortOrder,
    qdr,
    listFilters,
    fromFilters,
    apiPath,
    update,
    toggleFilter,
  }
}
