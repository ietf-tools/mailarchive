import type { ZodType } from 'zod'

/**
 * Fetch a JSON endpoint from the Django backend and validate it against its
 * Zod schema (the contract).
 *
 * - On the client the request is same-origin (dev proxy / nginx route
 *   `/arch/api/**` to Django), so the session cookie rides along.
 * - On the server (SSR) it goes straight to the backend and forwards the
 *   incoming request's cookie, so private-list authorization is honored
 *   exactly as Django's decorators enforce it.
 */
export async function useApi<T>(path: string, schema: ZodType<T>): Promise<T> {
  const config = useRuntimeConfig()
  const headers: Record<string, string> = {}
  let baseURL = config.public.apiBase

  if (import.meta.server) {
    baseURL = config.apiInternalBase
    Object.assign(headers, useRequestHeaders(['cookie']))
  }

  const data = await $fetch(path, {
    baseURL,
    headers,
    credentials: 'include',
  })
  return schema.parse(data)
}
