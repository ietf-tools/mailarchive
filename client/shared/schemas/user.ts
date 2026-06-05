import { z } from 'zod'

// Contract for GET /arch/api/v1/whoami/ (see backend web_api.whoami).
export const WhoAmISchema = z.object({
  authenticated: z.boolean(),
  username: z.string(),
  is_staff: z.boolean(),
  is_superuser: z.boolean(),
})

export type WhoAmI = z.infer<typeof WhoAmISchema>
