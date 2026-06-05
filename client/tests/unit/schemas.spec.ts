import { describe, it, expect } from 'vitest'
import { SearchResponseSchema } from '../../shared/schemas/search'
import { MessageDetailSchema } from '../../shared/schemas/message'
import { ListsResponseSchema } from '../../shared/schemas/list'
import { WhoAmISchema } from '../../shared/schemas/user'

// These guard against Django <-> frontend contract drift. In CI they would be
// run against a *live* seeded backend response; here we assert the schemas
// accept the documented payload shapes and reject malformed ones.

describe('search contract', () => {
  const sample = {
    results: [
      {
        url: '/arch/msg/pubone/abcd/',
        msgid: 'a01@example.com',
        subject: 'BBQ Invitation',
        frm: 'Zach <zach@example.com>',
        frm_name: 'Zach',
        date: '2013-02-01T00:00:00+00:00',
        email_list: 'pubone',
        thread_id: 7,
        thread_depth: 0,
        django_id: '12',
      },
    ],
    aggregations: {
      list_terms: [{ key: 'pubone', doc_count: 5 }],
      from_terms: [{ key: 'Zach', doc_count: 1 }],
    },
    count: 1,
    page: 1,
    num_pages: 1,
    has_next: false,
    has_previous: false,
    results_per_page: 20,
    group_by_thread: false,
    queryid: 'deadbeef',
  }

  it('parses a well-formed response', () => {
    expect(() => SearchResponseSchema.parse(sample)).not.toThrow()
  })

  it('allows null queryid and missing facet groups', () => {
    expect(() =>
      SearchResponseSchema.parse({ ...sample, queryid: null, aggregations: {} }),
    ).not.toThrow()
  })

  it('rejects a wrong-typed count', () => {
    expect(() => SearchResponseSchema.parse({ ...sample, count: '1' })).toThrow()
  })
})

describe('message detail contract', () => {
  const sample = {
    msgid: 'a01@example.com',
    subject: 'BBQ Invitation',
    frm: 'Zach <zach@example.com>',
    frm_name: 'Zach',
    to: 'to@amsl.com',
    cc: '',
    date: '2013-02-01T00:00:00+00:00',
    email_list: 'pubone',
    list_private: false,
    url: '/arch/msg/pubone/abcd/',
    download_url: '/arch/msg/pubone/abcd/download/',
    thread_id: 7,
    thread_depth: 0,
    body: '<p>Hello</p>',
    thread_snippet: '<ul></ul>',
    date_index_url: '/arch/browse/pubone/?index=abcd',
    thread_index_url: '/arch/browse/pubone/?gbt=1&index=abcd',
    nav: {
      previous_in_list: '',
      next_in_list: '/arch/msg/pubone/efgh/',
      previous_in_thread: '',
      next_in_thread: '',
    },
  }

  it('parses a well-formed message', () => {
    expect(() => MessageDetailSchema.parse(sample)).not.toThrow()
  })

  it('requires the nav block', () => {
    const { nav: _omit, ...withoutNav } = sample
    expect(() => MessageDetailSchema.parse(withoutNav)).toThrow()
  })
})

describe('lists + whoami contracts', () => {
  it('parses lists', () => {
    expect(() =>
      ListsResponseSchema.parse({
        lists: [{ name: 'pubone', description: '', private: false, active: true, message_count: 5 }],
      }),
    ).not.toThrow()
  })

  it('parses whoami', () => {
    expect(() =>
      WhoAmISchema.parse({
        authenticated: true,
        username: 'jay',
        is_staff: false,
        is_superuser: false,
      }),
    ).not.toThrow()
  })
})
