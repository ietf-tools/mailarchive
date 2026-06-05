# Mail Archive — Nuxt frontend (proof of concept)

A Vue 3 + Nuxt 4 (SSR) frontend for the IETF Mail Archive, modeled on the
[ietf-tools/red](https://github.com/ietf-tools/red) stack: Reka UI + Tailwind 4,
Pinia (+ persistence), `$fetch`/`useAsyncData`, and **Zod schemas as the API
contract**. Oxlint + Prettier, Vitest + Playwright, vue-tsc.

This is a **proof of concept** covering the public read pages — Home, Browse
(list of lists), Search, and Message detail — at their existing `/arch/...`
URLs. The Django backend is unchanged except for additive JSON endpoints under
`/arch/api/v1/`; all data, search (Elasticsearch), and authorization stay in
Django.

## Architecture

```
Browser ──► Nuxt SSR (:3000)
              │  pages render via useAsyncData/$fetch + Zod validation
              └─ /arch/api/v1/** ──proxy──► Django (:8000)
```

- **Client** fetches `/arch/api/v1/...` same-origin (dev proxy / nginx route).
- **SSR** fetches the backend directly and forwards the incoming session
  cookie (`useApi` in `app/composables/useApi.ts`), so private-list access is
  honored server-side.
- The browser JSON API (`/arch/api/v1/`, session cookie) is separate from the
  existing machine API (`/api/v1/`, X-API-KEY).

## Layout

- `app/pages/arch/` — routes mirroring the Django URLs (permalink-preserving)
- `app/components/{common,browse,search,message}/` — UI
- `app/composables/` — `useApi`, `useSearchQuery` (URL ↔ state)
- `app/stores/` — Pinia: `search` (UI state, persisted), `user` (whoami)
- `shared/schemas/` — Zod contract (`search`, `message`, `list`, `user`)

## Develop

Run the Django backend first (Postgres + Elasticsearch + sample data + built
index), serving on `:8000`. Then:

```bash
cd client
npm install
npm run dev          # http://localhost:3000/arch/
```

Or via the dev stack (Django served in the `app` container):

```bash
docker compose -f compose-dev.yml up client
```

Set `NUXT_DEV_PROXY_TARGET` / `NUXT_API_INTERNAL_BASE` to point at the backend
(`http://localhost:8000` locally, `http://app:8000` in compose).

## Quality

```bash
npm run typecheck    # nuxt prepare + vue-tsc
npm run lint         # oxlint
npm run format:check # prettier
npm run test         # vitest (Zod contract tests)
npm run test:e2e     # playwright (needs :3000 + :8000 running)
npm run build        # production build
```
