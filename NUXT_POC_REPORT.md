# Post-Implementation Report — Vue 3 + Nuxt 4 Frontend (Proof of Concept)

**Project:** IETF Mail Archive (`mailarchive`)

**Branch:** `jay-ai-demonstration`

**Commits (on the branch):** `4cb2c38b` (backend `/arch/api/v1/` + Nuxt scaffold), `58dbe6be` (this report), `88c70ddd` (demo settings module), plus a styling commit adding exact visual parity with the live site.

**Reference architecture:** [ietf-tools/red](https://github.com/ietf-tools/red)

---

## 1. Objective

Demonstrate that the `ietf-tools/red` frontend architecture (Nuxt 4 + Vue 3 SSR, Pinia, `$fetch`/`useAsyncData`, Zod-as-contract) can drive the Mail Archive UI, by converting a representative slice of the public, read-only pages end-to-end — while leaving the existing Django application fully intact. A later iteration restyled those pages to look exactly like the current live site (see section 4.5).

The fundamental difference from `red`: `red` has no Django (it consumes external APIs + Typesense). Mail Archive keeps its Django backend (Elasticsearch, OIDC, Celery, blobdb), so the PoC is Django-as-API-backend + Nuxt-as-frontend, with Django remaining the single data and authorization authority.

## 2. Scope & decisions

Agreed with the project owner before implementation:

| Decision | Choice | Rationale |
|---|---|---|
| Ambition | Proof of concept | Demonstrate the stack on a few representative pages; not a production cutover. |
| Pages | Public read pages only | Home, Browse (list of lists), Search, Message detail. Admin/spam triage, static index pages, exports, reports stay on Django. |
| API contract | Hand-rolled Django JSON + Zod | Most faithful to `red` (Zod is the source of truth, no OpenAPI codegen); lowest new-dependency churn; the model already serializes itself. |
| Rendering | SSR | Matches `red`; important for archive permalinks and SEO. |
| Visual style | Match the live site exactly | Reuse the live site's own stylesheets and reproduce the template markup (added after the initial build). |

Pages explicitly out of scope: advanced search, admin console, admin spam/message triage, static index pages, exports, reports, and the message-detail Cloudflare Worker.

## 3. Target architecture

```
Browser ──► Nuxt 4 SSR (:3000)
              │  pages render via useAsyncData/$fetch + Zod validation
              └─ /arch/api/v1/** ──proxy──► Django (:8000)
                                              │ reuses ES, models, decorators
                                              └─ Postgres / Elasticsearch
```

- Client fetches `/arch/api/v1/...` same-origin (dev proxy in dev; nginx route in prod), so the Django session cookie rides along automatically.
- SSR fetches the backend directly and forwards the incoming request's cookie (`useApi` → `useRequestHeaders(['cookie'])`), so private-list authorization is honored server-side exactly as Django's decorators enforce it.
- The browser JSON API (`/arch/api/v1/`, session-cookie auth) is deliberately separate from the existing machine API (`/api/v1/`, X-API-KEY, `csrf_exempt`).

## 4. What was built

### 4.1 Backend (additive only)

- `backend/mlarchive/archive/web_api.py` — four session-cookie JSON views under `/arch/api/v1/`: `whoami`, `lists`, `search` (Elasticsearch results + facet aggregations + pagination + sort + date/thread grouping), and `msg/<list>/<id>/` (full message detail with rendered body HTML, thread snippet, nav links).
- `backend/mlarchive/archive/urls.py` — routes wired under `arch/api/v1/`.
- `backend/mlarchive/tests/archive/web_api.py` — 12 pytest cases following existing conventions.

### 4.2 Reuse of existing code (no reinvention)

| New endpoint | Reused existing logic |
|---|---|
| `search` | `AdvancedSearchForm`, `search_from_form()`, `CustomPaginator`, `results.aggregations`, `get_count()` |
| `msg` | `@pad_id` + `@check_access` decorators (verbatim), `Message.get_body_html()`, `get_thread_snippet()`, `previous/next_in_list/thread()`, `get_absolute_url()` |
| `lists` | `get_lists_for_user()` (private-list visibility) |
| errors | `HttpJson400/404` + existing `JsonExceptionMiddleware` |

Because `@check_access` is preserved on the detail view, the 301-redirect (moved), 410 (removed), and 403 (private) behaviors are inherited unchanged, and unpadded hashcode permalinks still resolve.

### 4.3 Frontend (`client/`)

Built on the `red` stack: Nuxt 4.4 SSR, Vue 3.5, Pinia + `pinia-plugin-persistedstate`, data fetching via `$fetch`/`useAsyncData` with Zod schemas in `client/shared/schemas/` as the API contract (validated at runtime in `app/composables/useApi.ts`). `app/composables/useSearchQuery.ts` makes the URL the single source of truth for search state (`navigateTo({ query }, { replace: true })`), mirroring `red`'s pattern, and the Pinia `search` store holds UI/preference state only. Pages mirror the Django URLs exactly (`pages/arch/...`), preserving permalinks. Tooling: exact-version `.npmrc`, Oxlint + Prettier (single quotes, no semicolons), Vitest (Zod contract tests) + Playwright (e2e), vue-tsc.

The initial build used Reka UI + Tailwind 4 for styling; that was subsequently replaced (section 4.5) to match the live site, and the now-unused `tailwindcss`, `@tailwindcss/vite`, `reka-ui`, `@nuxt/icon`, and `@iconify-json/lucide` packages were pruned.

### 4.4 Dev integration

`compose-dev.yml` gains a `client` service (Node 24, port 3000) that proxies `/arch/api` → the `app` container. The Nitro dev proxy target and SSR backend base are env-configurable (`NUXT_DEV_PROXY_TARGET`, `NUXT_API_INTERNAL_BASE`).

### 4.5 Visual styling — exact parity with the live site

The demo pages were restyled to look exactly like their counterparts at `https://mailarchive.ietf.org/`. Rather than re-implement the look, the demo loads the live site's own stylesheets and reproduces the Django templates' markup, so the result matches by construction.

- The actual compiled stylesheets (`bootstrap_custom.css`, `styles.css`), Font Awesome, the Bootstrap JS bundle, the theme script (`bs-theme.js`), and the IETF logo were copied from the repo into `client/public/vendor/` and loaded via `<head>` links/scripts in `nuxt.config.ts` (with `data-bs-theme="auto"`, matching the live site's light/dark behavior).
- Each Vue component reproduces the exact markup and class names of its Django template: `base.html` (navbar, footer, `#container`/`#content`), `main.html` (home `.search-wrapper`), `browse.html` (`.browse-page` sections + `.browse-column`/`.browse-list`), `search.html` (the `#msg-container` 3-pane: sidebar filters, toolbar, `#list-pane` headers + `.xtable` rows, controls, splitter, view-pane), and `detail.html` (`#msg-body` from `get_body_html()` + `#message-thread` snippet + `navbar-msg-detail`).
- A `pages/arch/browse/[list].vue` route was added so the live `/arch/browse/<list>/` view (the results 3-pane in browse mode) has a direct demo counterpart, sharing the `SearchResults` component with `/arch/search/`.

## 5. Verification

### 5.1 Frontend (local Node)

| Check | Result |
|---|---|
| `npm install` + `nuxt prepare` | ✅ 0 vulnerabilities, types generated |
| `vitest` (Zod contract tests) | ✅ 7/7 pass |
| `vue-tsc --noEmit` typecheck | ✅ clean |
| `oxlint` | ✅ clean |
| `nuxt build` (production) | ✅ Nitro server built (bundle 3.51 MB / 868 kB gzip after pruning) |
| SSR runtime smoke test | ✅ `/arch/`, `/arch/browse/`, `/arch/search/` all 200, server-rendered |

### 5.2 Backend (inside the devcontainer)

Built and ran the actual devcontainer stack (`compose-dev.yml` + `.devcontainer/docker-compose.extend.yml`): `app` + Postgres 17 + Elasticsearch 7.17 (security enabled) + RabbitMQ + blobstore.

| Check | Result |
|---|---|
| Build `app` image | ✅ `mailarchive-app` built |
| Elasticsearch / Postgres | ✅ green / ready |
| New `tests/archive/web_api.py` | ✅ 12 passed |
| Existing `tests/archive/api.py` + `views.py` (regression) | ✅ 104 passed, 2 skipped |
| `manage.py check` | ✅ no issues |

The new endpoints are validated end-to-end against the real search backend: facets/aggregations, pagination, private-list exclusion (anonymous vs member), and the message-detail access decorators. No regression to the existing API/view tests.

### 5.3 Live demo + visual parity

The complete demo was brought up and exercised through the browser path (Nuxt SSR → dev proxy → Django → Elasticsearch/Postgres), using a dedicated `demo` settings module (see Observation 8) and three lists loaded from the bundled mbox fixtures (`acme`, `ford`, `dnsop` — 9 messages, indexed to `demo-mail-archive`). Each page was screenshot-compared against its live counterpart and confirmed to match (navbar colour verified as `rgb(51,122,183)`, the production blue; Font Awesome and the real stylesheets confirmed loaded).

| Page (via Nuxt on `:3000`) | Result |
|---|---|
| `/arch/` | ✅ Blue navbar + logo + "Mail Archive" + Help dropdown; centered `.search-wrapper`; "Advanced Search \| Browse" |
| `/arch/browse/` | ✅ `(choose list)` + Go; bordered section headings; `.browse-column` link grid |
| `/arch/browse/<list>/` (e.g. `acme`) | ✅ 3-pane: "Viewing List" + time/from filters + sidebar footer; back-arrow + Date/Thread tabs + search + Export; sortable Subject/From/Date headers; `YYYY-MM-DD` dates; "N Messages / Page X of Y" |
| `/arch/msg/<list>/<id>/` | ✅ Date/Thread nav bars; `#msg-body` (download/link icons, subject, `From \| Date`, `<pre>` payload); highlighted thread snippet; "Hide Navigation Bar" |
| `/arch/api/v1/{whoami,lists,search}` (Django `:8000`) | ✅ 200, real JSON |

## 6. Observations & caveats

1. **`/api/v1/` namespace collision (resolved by design).** The existing `/api/v1/` is the X-API-KEY machine API, keyed by exact path in `settings.API_KEYS` and `csrf_exempt`. Putting the browser JSON under `/arch/api/v1/` (session cookie + normal CSRF) keeps the two auth models from mixing — a safety win, and it matches `red`'s convention of proxying `/arch/...` to Nuxt while machine APIs stay elsewhere.

2. **Test settings depend on a live broker.** The repo's `backend/mlarchive/settings/test.py` leaves blob replication enabled, so saving a `Message` enqueues a Celery task. Without a `.env`, `CELERY_BROKER_URL` defaults to `amqp://` (i.e. `127.0.0.1:5672`), which is empty in the `app` container, so the message tests fail with `kombu ... Connection refused`. The CI copy (`dev/tests/test.py`, swapped in by `dev/tests/prepare.sh`) instead sets `BLOBDB_REPLICATION['ENABLED'] = False`. A normal devcontainer works because `app-init.sh` writes `.env` pointing the broker at the `rabbit` container. We reproduced that by passing `CELERY_BROKER_URL=amqp://guest:guest@rabbit:5672//`. Optional cleanup (out of scope): align the repo `test.py` with CI by disabling replication, so the suite doesn't depend on a live broker.

3. **Cloudflare Worker / anonymous permalinks.** `workers/messages/` already serves anonymous `/arch/msg/` from R2 and only proxies to origin when a session cookie is present. For productionization this means the highest-traffic, most SEO-sensitive path can stay on the proven Worker path while authenticated detail moves to Nuxt first — decoupling the rollout from permalink/SEO risk.

4. **SSR + private content.** Forwarding the browser cookie on SSR is the subtle part: authenticated/private responses must be marked non-cacheable to avoid cross-user SSR cache poisoning. The backend already sets never-cache headers for private lists.

5. **Devcontainer ES has security enabled.** `.devcontainer/docker-compose.extend.yml` overrides `es` to `xpack.security.enabled=true` (CI uses it disabled). The repo `test.py` uses `http_auth=('elastic','changeme')`, which matches `ELASTIC_PASSWORD`, so both configurations work.

6. **Node engine warning (benign).** `npm install` emitted `EBADENGINE` warnings — a few transitive postcss packages want Node ≥24.11 (host has 24.10). Warnings only; the build succeeds.

7. **Styling reuses the live CSS verbatim.** Exact visual parity was achieved by loading the live site's actual `bootstrap_custom.css` + `styles.css` + Font Awesome (copied into `client/public/vendor/`) and reproducing the template markup, rather than re-implementing the look in a utility framework. This is why the match is exact. One behavior is approximated: the search preview pane's drag splitter (originally driven by `mailarch.js`) uses a fixed 45/55 split in the demo; all other styling is the genuine CSS. `data-bs-theme="auto"` means the demo follows the OS light/dark preference, exactly like the live site.

8. **Dev blob-storage misroutes its Postgres connection (pre-existing bug, worked around).** Under `docker-development`, `Message.save()` (and the loader, and ES indexing that reads the body) hits the blobdb storage, which connects to the `db` container (`172.18.0.5`) using the `mailarch` role — but that role only exists on the `blobdb` container (`172.18.0.8`), so it fails with `role "mailarch" does not exist`. Notably, `migrate --database=blobdb` connects to the correct blobdb host, so Django's `blobdb` database alias is configured fine — the storage layer builds a different (mis-host'd) connection. Chasing this is orthogonal to the PoC, so the demo uses a small `backend/mlarchive/settings/demo.py` that does what `settings/test.py` already does successfully: route blob models to the default database (`BLOBDB_DATABASE = 'default'`, `DATABASE_ROUTERS = []`), disable replication, and use a dedicated `demo-mail-archive` ES index — but against the persistent dev DB so data survives restarts. Recommended follow-up (out of scope): fix the blobdb storage connection so the full dev blob pipeline works, or document `demo.py` as the supported way to run a self-contained instance without the blob-import pipeline.

## 7. Productionization path (NOT built in this PoC)

Deployment is a single multi-container pod, and `k8s/nginx-mailarchive.conf` is the one routing file. To productionize via a strangler migration:

1. Add the Nuxt SSR server as a sidecar (`:3000`); add a `mailarchive_nuxt` upstream plus `/_nuxt/` and `/arch/api/` locations to nginx.
2. Migrate page-by-page by adding one nginx `location` per page (cookie/percentage canaries; rollback = delete the `location`). Default route stays Django, so un-migrated = unchanged.
3. Keep anonymous `/arch/msg/` on the Cloudflare Worker; migrate authenticated detail first.
4. Build the Nuxt app as a separate image in CI; never delete a Django view/template until its Nuxt replacement has soaked at 100% in production.

If the live-site CSS is kept, the production build should serve `bootstrap_custom.css`/`styles.css`/Font Awesome from Django's static pipeline (or a shared package) rather than the copies under `client/public/vendor/`, so there is a single source of truth for styling.

## 8. Known limitations

- The full login/logout flow needs the same-origin nginx (or backend origin); the dev proxy only forwards `/arch/api`. The "Sign in" link points at Django's `/accounts/login/`.
- Pages out of scope (advanced search, admin, static index, exports, reports) remain on Django and are unchanged.
- Playwright e2e and the full pytest suite (incl. Selenium/Playwright functional tests) were not executed end-to-end here; the e2e specs are provided and run against a live `:3000` + `:8000`.
- The vendored stylesheets/fonts under `client/public/vendor/` are copies of the live site's assets, committed so the demo is self-contained; they would be de-duplicated for production (see section 7).

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

### Running the full live demo (with data)

```bash
DC="docker compose -f compose-dev.yml -f .devcontainer/docker-compose.extend.yml"

# 1. Start all required services
$DC up -d app db es rabbit blobstore blobdb memcached

# 2. Initialize the app (creates .env, configures blobstore, migrates)
$DC exec -e EDITOR_VSCODE=true app /docker-init.sh

# 3. Migrate + load sample lists + build the index, using the demo settings
$DC exec -e DJANGO_SETTINGS_MODULE=mlarchive.settings.demo \
         -e CELERY_BROKER_URL=amqp://guest:guest@rabbit:5672// app bash -lc '
  cd /workspace/backend
  python manage.py migrate --noinput
  D=/workspace/backend/mlarchive/tests/data
  python manage.py load $D/search_api.mbox      --listname acme  --summary
  python manage.py load $D/search_api_ford.mbox --listname ford  --summary
  python manage.py load $D/urlize.mbox          --listname dnsop --summary
  python manage.py rebuild_index --noinput'

# 4. Start Django (detached, in the container) on :8000
$DC exec -d -e DJANGO_SETTINGS_MODULE=mlarchive.settings.demo \
            -e CELERY_BROKER_URL=amqp://guest:guest@rabbit:5672// \
  app bash -lc 'cd /workspace/backend && python manage.py runserver 0.0.0.0:8000'

# 5. Start Nuxt on the host (proxies /arch/api -> :8000)
cd client && npm run dev        # open http://localhost:3000/arch/
```

Note: the message-detail body renders because the mbox loader stores the raw message (in `demo` mode, to the default DB / `ARCHIVE_DIR`). Factory-only seeding would leave bodies empty.

## 10. File inventory

Backend (commit `4cb2c38b`): `backend/mlarchive/archive/web_api.py` (new), `backend/mlarchive/archive/urls.py` (modified — routes), `backend/mlarchive/tests/archive/web_api.py` (new — 12 tests).

Demo settings (commit `88c70ddd`): `backend/mlarchive/settings/demo.py` (new — runnable demo settings; see Observation 8).

Frontend (`client/`): the Nuxt app — `nuxt.config.ts`, `app/` (pages, layouts, components, composables `useApi`/`useSearchQuery`, stores `search`/`user`), `shared/schemas/` (Zod contract), `tests/unit` (Vitest) + `tests/e2e` (Playwright), tooling configs, `README.md`.

Styling (live-site parity): `client/public/vendor/` (copied `bootstrap_custom.css`, `styles.css`, Font Awesome, `bootstrap.bundle.min.js`, `bs-theme.js`, logo, splitter grip); rewritten `app/components/common/AppHeader.vue` + `AppFooter.vue`; `app/layouts/{default,scrolling,results}.vue`; `app/pages/arch/{index,search}.vue`, `app/pages/arch/browse/{index,[list]}.vue`, `app/pages/arch/msg/[list]/[id].vue`; `app/components/search/SearchResults.vue` (new) and `app/components/message/DetailNavbar.vue`; `.claude/launch.json` (preview); pruned deps in `package.json`.

Dev (`compose-dev.yml`): adds a `client` dev service (`:3000`).

## 11. Recommended next steps

1. Decide whether to align the repo `test.py` with CI (`BLOBDB_REPLICATION['ENABLED'] = False`) so the suite doesn't require a live broker.
2. Investigate the dev blob-storage connection bug (Observation 8) so the full `docker-development` blob pipeline works without the `demo.py` workaround.
3. Run the Playwright e2e against the live Django + Nuxt + sample data now running.
4. If proceeding beyond the PoC, scaffold the strangler nginx routing and the Nuxt sidecar image, serve the shared stylesheets from a single source (section 7), and migrate the first low-risk page behind a canary.
