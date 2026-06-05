# Post-Implementation Report — Vue 3 + Nuxt 4 Frontend (Proof of Concept)

**Project:** IETF Mail Archive (`mailarchive`)
**Branch:** `jay-ai-demonstration`
**Commit:** `4cb2c38b` — *feat: add Vue 3 + Nuxt 4 frontend proof of concept*
**Date:** 2026-06-05
**Reference architecture:** [ietf-tools/red](https://github.com/ietf-tools/red)

---

## 1. Objective

Demonstrate that the `ietf-tools/red` frontend architecture (Nuxt 4 + Vue 3 SSR,
Reka UI + Tailwind 4, Pinia, `$fetch`/`useAsyncData`, Zod-as-contract) can drive
the Mail Archive UI, by converting a representative slice of the public,
read-only pages end-to-end — while leaving the existing Django application fully
intact.

The fundamental difference from `red`: `red` has **no Django** (it consumes
external APIs + Typesense). Mail Archive keeps its Django backend (Elasticsearch,
OIDC, Celery, blobdb), so the PoC is **Django-as-API-backend + Nuxt-as-frontend**,
with Django remaining the single data and authorization authority.

## 2. Scope & decisions

Agreed with the project owner before implementation:

| Decision | Choice | Rationale |
|---|---|---|
| Ambition | **Proof of concept** | Demonstrate the stack on a few representative pages; not a production cutover. |
| Pages | **Public read pages only** | Home, Browse (list of lists), Search, Message detail. Admin/spam triage, static index pages, exports, reports stay on Django. |
| API contract | **Hand-rolled Django JSON + Zod** | Most faithful to `red` (Zod is the source of truth, no OpenAPI codegen); lowest new-dependency churn; the model already serializes itself. |
| Rendering | **SSR** | Matches `red`; important for archive permalinks and SEO. |

Pages explicitly **out of scope**: advanced search, admin console, admin spam/message
triage, static index pages, exports, reports, and the message-detail Cloudflare Worker.

## 3. Target architecture

```
Browser ──► Nuxt 4 SSR (:3000)
              │  pages render via useAsyncData/$fetch + Zod validation
              └─ /arch/api/v1/** ──proxy──► Django (:8000)
                                              │ reuses ES, models, decorators
                                              └─ Postgres / Elasticsearch
```

- **Client fetches** `/arch/api/v1/...` same-origin (dev proxy in dev; nginx route
  in prod), so the Django session cookie rides along automatically.
- **SSR fetches** the backend directly and forwards the incoming request's cookie
  (`useApi` → `useRequestHeaders(['cookie'])`), so private-list authorization is
  honored server-side exactly as Django's decorators enforce it.
- The browser JSON API (`/arch/api/v1/`, session-cookie auth) is **deliberately
  separate** from the existing machine API (`/api/v1/`, X-API-KEY, `csrf_exempt`).

## 4. What was built

### 4.1 Backend (additive only)

- **`backend/mlarchive/archive/web_api.py`** — four session-cookie JSON views under
  `/arch/api/v1/`:
  - `GET /whoami/` — auth state for the UI (authorization always stays server-side).
  - `GET /lists/` — private-aware list of lists with message counts.
  - `GET /search/` — Elasticsearch results + facet aggregations + pagination + sort +
    date/thread grouping.
  - `GET /msg/<list>/<id>/` — full message detail (rendered body HTML, thread snippet,
    nav links).
- **`backend/mlarchive/archive/urls.py`** — routes wired under `arch/api/v1/`.
- **`backend/mlarchive/tests/archive/web_api.py`** — 12 pytest cases following existing
  conventions.

### 4.2 Reuse of existing code (no reinvention)

| New endpoint | Reused existing logic |
|---|---|
| `search` | `AdvancedSearchForm`, `search_from_form()`, `CustomPaginator`, `results.aggregations`, `get_count()` |
| `msg` | `@pad_id` + `@check_access` decorators (verbatim), `Message.get_body_html()`, `get_thread_snippet()`, `previous/next_in_list/thread()`, `get_absolute_url()` |
| `lists` | `get_lists_for_user()` (private-list visibility) |
| errors | `HttpJson400/404` + existing `JsonExceptionMiddleware` |

Because `@check_access` is preserved on the detail view, the **301-redirect (moved),
410 (removed), and 403 (private) behaviors are inherited unchanged**, and unpadded
hashcode permalinks still resolve.

### 4.3 Frontend (`client/`) — the `red` stack

- Nuxt 4.4 SSR, Vue 3.5, Reka UI (resizable splitter for the detail-preview pane),
  Tailwind 4, Nuxt Icon, Pinia + `pinia-plugin-persistedstate`.
- Data fetching via `$fetch`/`useAsyncData`; **Zod schemas in `client/shared/schemas/`
  are the API contract**, validated at runtime in `app/composables/useApi.ts`.
- `app/composables/useSearchQuery.ts` makes the **URL the single source of truth** for
  search state (`navigateTo({ query }, { replace: true })`), mirroring `red`'s pattern.
- Pinia `search` store holds **UI/preference state only** (selectively persisted);
  the query lives in the URL.
- Pages mirror the Django URLs exactly (`pages/arch/...`), preserving permalinks.
- Tooling: exact-version `.npmrc`, Oxlint + Prettier (single quotes, no semicolons),
  Vitest (Zod contract tests) + Playwright (e2e), vue-tsc.

### 4.4 Dev integration

- `compose-dev.yml` gains a `client` service (Node 24, port 3000) that proxies
  `/arch/api` → the `app` container.
- The Nitro dev proxy target and SSR backend base are env-configurable
  (`NUXT_DEV_PROXY_TARGET`, `NUXT_API_INTERNAL_BASE`).

## 5. Verification

### 5.1 Frontend (local Node)

| Check | Result |
|---|---|
| `npm install` + `nuxt prepare` | ✅ 0 vulnerabilities, types generated |
| `vitest` (Zod contract tests) | ✅ 7/7 pass |
| `vue-tsc --noEmit` typecheck | ✅ clean |
| `oxlint` | ✅ clean |
| `nuxt build` (production) | ✅ Nitro server built |
| SSR runtime smoke test | ✅ `/arch/`, `/arch/browse/`, `/arch/search/` all 200, server-rendered |

The SSR smoke test was run with **no backend up**, confirming pages render and
data-fetch failures degrade gracefully.

### 5.2 Backend (inside the devcontainer)

Built and ran the actual devcontainer stack
(`compose-dev.yml` + `.devcontainer/docker-compose.extend.yml`): `app` +
Postgres 17 + Elasticsearch 7.17 (security enabled) + RabbitMQ + blobstore.

| Check | Result |
|---|---|
| Build `app` image | ✅ `mailarchive-app` built |
| Elasticsearch / Postgres | ✅ green / ready |
| **New `tests/archive/web_api.py`** | ✅ **12 passed** |
| Existing `tests/archive/api.py` + `views.py` (regression) | ✅ **104 passed, 2 skipped** |
| `manage.py check` | ✅ no issues |

The new endpoints are validated end-to-end against the real search backend:
facets/aggregations, pagination, private-list exclusion (anonymous vs member), and
the message-detail access decorators. No regression to the existing API/view tests.

## 6. Observations & caveats

1. **`/api/v1/` namespace collision (resolved by design).** The existing `/api/v1/`
   is the X-API-KEY *machine* API, keyed by exact path in `settings.API_KEYS` and
   `csrf_exempt`. Putting the browser JSON under **`/arch/api/v1/`** (session cookie +
   normal CSRF) keeps the two auth models from mixing — a safety win, and it matches
   `red`'s convention of proxying `/arch/...` to Nuxt while machine APIs stay elsewhere.

2. **Test settings depend on a live broker.** The repo's
   `backend/mlarchive/settings/test.py` leaves **blob replication enabled**, so saving
   a `Message` enqueues a Celery task. Without a `.env`, `CELERY_BROKER_URL` defaults to
   `amqp://` (i.e. `127.0.0.1:5672`), which is empty in the `app` container → the message
   tests fail with `kombu ... Connection refused`. The CI copy
   (`dev/tests/test.py`, swapped in by `dev/tests/prepare.sh`) instead sets
   `BLOBDB_REPLICATION['ENABLED'] = False`. A normal devcontainer works because
   `app-init.sh` writes `.env` pointing the broker at the `rabbit` container.
   We reproduced that by passing `CELERY_BROKER_URL=amqp://guest:guest@rabbit:5672//`.
   **Optional cleanup (out of scope):** align the repo `test.py` with CI by disabling
   replication, so the suite doesn't depend on a live broker.

3. **Cloudflare Worker / anonymous permalinks.** `workers/messages/` already serves
   *anonymous* `/arch/msg/` from R2 and only proxies to origin when a session cookie is
   present. For productionization this means the highest-traffic, most SEO-sensitive
   path can stay on the proven Worker path while authenticated detail moves to Nuxt
   first — decoupling the rollout from permalink/SEO risk.

4. **SSR + private content.** Forwarding the browser cookie on SSR is the subtle part:
   authenticated/private responses must be marked non-cacheable to avoid cross-user SSR
   cache poisoning. The backend already sets never-cache headers for private lists.

5. **Devcontainer ES has security enabled.** `.devcontainer/docker-compose.extend.yml`
   overrides `es` to `xpack.security.enabled=true` (CI uses it disabled). The repo
   `test.py` uses `http_auth=('elastic','changeme')`, which matches `ELASTIC_PASSWORD`,
   so both configurations work.

6. **Node engine warning (benign).** `npm install` emitted `EBADENGINE` warnings —
   a few transitive postcss packages want Node ≥24.11 (host has 24.10). Warnings only;
   the build succeeds.

7. **Reka UI used directly, not via its Nuxt module.** Splitter components are imported
   explicitly (`from 'reka-ui'`) and components use flat names
   (`components: [{ path: '~/components', pathPrefix: false }]`) to keep the build
   robust and predictable.

## 7. Productionization path (NOT built in this PoC)

Deployment is a single multi-container pod, and `k8s/nginx-mailarchive.conf` is the one
routing file. To productionize via a **strangler** migration:

1. Add the Nuxt SSR server as a **sidecar** (`:3000`); add a `mailarchive_nuxt` upstream
   plus `/_nuxt/` and `/arch/api/` locations to nginx.
2. Migrate page-by-page by adding **one nginx `location` per page** (cookie/percentage
   canaries; rollback = delete the `location`). Default route stays Django, so
   un-migrated = unchanged.
3. Keep anonymous `/arch/msg/` on the Cloudflare Worker; migrate authenticated detail
   first.
4. Build the Nuxt app as a separate image in CI; never delete a Django view/template
   until its Nuxt replacement has soaked at 100% in production.

## 8. Known limitations

- The full login/logout flow needs the same-origin nginx (or backend origin); the dev
  proxy only forwards `/arch/api`. The "Sign in" link points at Django's
  `/accounts/login/`.
- Pages out of scope (advanced search, admin, static index, exports, reports) remain on
  Django and are unchanged.
- Playwright e2e and the full pytest suite (incl. Selenium/Playwright functional tests)
  were not executed end-to-end here; the e2e specs are provided and run against a live
  `:3000` + `:8000`.

## 9. How to run

### Frontend (local)

```bash
cd client
npm install
npm run dev          # http://localhost:3000/arch/   (needs Django on :8000)
npm run typecheck && npm run lint && npm run test && npm run build
```

### Devcontainer + backend tests

```bash
# build + start the stack
docker compose -f compose-dev.yml -f .devcontainer/docker-compose.extend.yml up -d app db es

# run the new endpoint tests
docker compose -f compose-dev.yml -f .devcontainer/docker-compose.extend.yml exec \
  -e DJANGO_SETTINGS_MODULE=mlarchive.settings.test \
  -e CELERY_BROKER_URL=amqp://guest:guest@rabbit:5672// \
  app bash -lc 'cd /workspace/backend/mlarchive && pytest tests/archive/web_api.py -v'

# stop the stack
docker compose -f compose-dev.yml -f .devcontainer/docker-compose.extend.yml down
```

## 10. File inventory (commit `4cb2c38b`)

**Backend**
- `backend/mlarchive/archive/web_api.py` *(new)*
- `backend/mlarchive/archive/urls.py` *(modified — routes)*
- `backend/mlarchive/tests/archive/web_api.py` *(new — 12 tests)*

**Frontend (`client/`)** — Nuxt app: `nuxt.config.ts`, `app/` (pages, layouts,
components for common/browse/search/message, composables `useApi`/`useSearchQuery`,
stores `search`/`user`, utilities), `shared/schemas/` (Zod contract), `tests/unit`
(Vitest) + `tests/e2e` (Playwright), tooling configs, `README.md`.

**Dev**
- `compose-dev.yml` *(modified — `client` service)*

## 11. Recommended next steps

1. Decide whether to align the repo `test.py` with CI (`BLOBDB_REPLICATION['ENABLED'] =
   False`) so the suite doesn't require a live broker.
2. Run the Playwright e2e against a live Django + Nuxt with sample data.
3. If proceeding beyond the PoC, scaffold the strangler nginx routing and the Nuxt
   sidecar image, and migrate the first low-risk page behind a canary.
