# The `spam_score` field

- Date: 2026-09-17
- Affects: `Message.spam_score` (`archive/models.py`), `settings/base.py`
  (`SPAM_SCORE_*`, `MARK_BITS`, `MARK_*`), the admin page, the removal
  pipeline, several `bin/` scripts

`Message.spam_score` is a single integer column, default 0, with the model
comment "> 0 = spam". In practice it carries three conventions that were
layered on over the years and are not compatible with each other. This note
records what is written into it, what reads it, and what the live data holds,
so the next person does not have to rediscover it.

## What writes it

### Whole-value sentinels

| value | constant | written by |
| --- | --- | --- |
| `-1` | `SPAM_SCORE_NOT_SPAM` | admin action "Mark not spam" via `utils.mark_not_spam()` |
| `1000` | `SPAM_SCORE_TO_REMOVE` | admin action "Remove" via `actions.remove_selected()`, cleared when the Celery task deletes the rows |
| `10` | `MARK_HTML` | nothing in current code |
| `11` | `MARK_LOAD_SPAM` | `bin/load_spam.py`, assigned to every message it imports "for later review" |
| any int | | `bin/check_spam.py --mark N` assigns the operator's integer to each message an inspector flags |

These are assignments, not ORs. `check_spam.py --mark` and `mark_not_spam()`
overwrite whatever was there.

### Bit flags

`settings.MARK_BITS` defines flags meant to be OR'd in:

| bit | name | set by |
| --- | --- | --- |
| 1 | `NON_ASCII_HEADER` | nothing in current code |
| 2 | `NO_RECVD_DATE` | nothing in current code |
| 4 | `NO_MSGID` | `MessageWrapper.get_msgid()` when the archive has to generate a Message-ID |
| 8 | `HAS_HTML_PART` | nothing in current code |

`Message.mark(bit)` ORs a bit in and saves. Only `NO_MSGID` is set by any
current code path.

### A hardcoded bit

`bin/corruption_identify.py` sets `0b00010000`, value 16, on a message and the
two following it when it finds an embedded `From ` line from the 2005-2008
mbox locking bug. `bin/corruption_remove.py` selects every message with bit 16
set as a removal candidate and deletes those that `exhibits_corruption()`
confirms. Neither script uses `MARK_BITS`, so nothing in settings reserves
this bit. Both scripts date from the 2020 import tooling.

### The conventions collide

Whole values and bit flags occupy the same integer. `11` is bits 1, 2 and 8, so
every `MARK_LOAD_SPAM` message also reads as `NON_ASCII_HEADER`,
`NO_RECVD_DATE` and `HAS_HTML_PART` to anyone testing bits. An operator value
such as `20240516` sets bits arbitrarily. Any new bit can therefore already be
"set" on rows that were never marked with it.

## What reads it

- **Admin page** (`views.admin`, `forms.AdminForm`): the `spam_score` field is
  an exact-match Elasticsearch `term` filter, and `exclude_not_spam` (on by
  default) excludes `-1`. Exact match means a row whose score combines several
  bits does not match a filter on any one of them. The view also warns when
  rows with `1000` are still waiting to be deleted.
- **Removal pipeline**: `actions.remove_selected()` sets `1000`, the
  `remove_selected` Celery task deletes every row with `1000`.
- **`bin/worker-checker.py`**: samples only public messages with
  `spam_score <= 0`, so any positive value excludes a message from the
  Cloudflare worker comparison.
- **`bin/batch_remove.py`, `bin/batch_remove_x.py`**: delete every message with
  an exact operator-supplied score. This is the consumer of `check_spam --mark`.
- **`bin/corruption_remove.py`**: bit 16, see above.
- **Elasticsearch**: indexed as an integer field so the admin filters work.

Nothing else reads it. Browse, search, detail, threading, the JSON blob, the
public API and the Cloudflare worker templates never consult it. The "> 0 =
spam" rule is a convention shared by the admin workflow and `worker-checker`,
not something enforced anywhere.

## What the data holds

Distribution on the populated dev database, 3,580,588 messages, 2026-09-17:

| spam_score | count | reading |
| --- | --- | --- |
| 0 | 3,319,151 | unmarked |
| 11 | 187,529 | `MARK_LOAD_SPAM` |
| -1 | 40,447 | marked not spam |
| 4 | 29,598 | `NO_MSGID` |
| 25 | 2,280 | bit 16 set, plus bits 1 and 8 |
| 20240516 | 1,533 | operator value from `check_spam --mark` |
| 119 | 41 | bit 16 set, plus bits 1, 2, 4, 32, 64 |
| 1 | 9 | `NON_ASCII_HEADER` |

2,321 messages have bit 16 set. `NO_MSGID` messages are not spam as a
population, see `history/generated_message_id.md`. The 40,447 rows at `-1`
are the only rows an admin has positively vouched for.

## Guidance

- Do not add new bit flags to this field. Bit 16 is taken by scripts that do
  not declare it, bit 32 and 64 already appear in operator values, and the
  exact-match admin filter cannot find a bit once it is combined with another.
  When the same-Message-ID feature needed to mark salted messages it started
  with a `DUPLICATE_MSGID` bit at 16, discovered the collision, and switched to
  deriving the state from the hashcode instead, see
  `history/duplicate_message_id_content.md`.
- Do not give a legitimate message a positive score. `worker-checker` and the
  admin convention both treat positive as spam.
- Treat `-1` and `1000` as the only values with defined behaviour in the web
  application. Everything else is operator bookkeeping from `bin/` scripts.
- If the field is ever cleaned up, the flags and the review markers want
  separate columns from the verdict. Until then, a query for "is this spam" is
  `spam_score > 0`, and a query for "did an admin clear this" is
  `spam_score == -1`, and neither is reliable for the 187,529 `load_spam`
  rows, which were marked for review rather than judged.
