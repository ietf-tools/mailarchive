import { z } from 'zod'

// Contract for GET /arch/api/v1/msg/<list>/<id>/ (see backend
// web_api.message_detail / serialize_message_detail).
export const MessageNavSchema = z.object({
  previous_in_list: z.string(),
  next_in_list: z.string(),
  previous_in_thread: z.string(),
  next_in_thread: z.string(),
})

export const MessageDetailSchema = z.object({
  msgid: z.string(),
  subject: z.string(),
  frm: z.string(),
  frm_name: z.string(),
  to: z.string(),
  cc: z.string(),
  date: z.string(),
  email_list: z.string(),
  list_private: z.boolean(),
  url: z.string(),
  download_url: z.string(),
  thread_id: z.number().nullable(),
  thread_depth: z.number(),
  body: z.string(),
  thread_snippet: z.string(),
  date_index_url: z.string(),
  thread_index_url: z.string(),
  nav: MessageNavSchema,
})

export type MessageNav = z.infer<typeof MessageNavSchema>
export type MessageDetail = z.infer<typeof MessageDetailSchema>
