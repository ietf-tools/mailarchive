import { z } from 'zod'

// Contract for GET /arch/api/v1/lists/ (see backend web_api.lists).
export const EmailListSchema = z.object({
  name: z.string(),
  description: z.string(),
  private: z.boolean(),
  active: z.boolean(),
  message_count: z.number(),
})

export const ListsResponseSchema = z.object({
  lists: z.array(EmailListSchema),
})

export type EmailList = z.infer<typeof EmailListSchema>
export type ListsResponse = z.infer<typeof ListsResponseSchema>
