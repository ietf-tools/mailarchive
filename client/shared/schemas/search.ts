import { z } from 'zod'

// Contract for GET /arch/api/v1/search/ (see backend web_api.search).
// Field names mirror the Elasticsearch document built by full_prepare().
export const SearchHitSchema = z.object({
  url: z.string(),
  msgid: z.string(),
  subject: z.string(),
  frm: z.string(),
  frm_name: z.string(),
  date: z.string(),
  email_list: z.string(),
  thread_id: z.number().nullable(),
  thread_depth: z.number(),
  django_id: z.string(),
})

export const FacetBucketSchema = z.object({
  key: z.string(),
  doc_count: z.number(),
})

export const AggregationsSchema = z.object({
  list_terms: z.array(FacetBucketSchema).optional(),
  from_terms: z.array(FacetBucketSchema).optional(),
})

export const SearchResponseSchema = z.object({
  results: z.array(SearchHitSchema),
  aggregations: AggregationsSchema,
  count: z.number(),
  page: z.number(),
  num_pages: z.number(),
  has_next: z.boolean(),
  has_previous: z.boolean(),
  results_per_page: z.number(),
  group_by_thread: z.boolean(),
  queryid: z.string().nullable(),
})

export type SearchHit = z.infer<typeof SearchHitSchema>
export type FacetBucket = z.infer<typeof FacetBucketSchema>
export type Aggregations = z.infer<typeof AggregationsSchema>
export type SearchResponse = z.infer<typeof SearchResponseSchema>
