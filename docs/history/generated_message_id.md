# Archive-generated Message-IDs

- Status: Accepted
- Date: 2026-08-28
- Affects: `archive/mail.py` (`MessageWrapper.get_msgid`, `MessageWrapper.write_msg`, `Loader`)

## Context

A message that arrives without a `Message-ID` header, and without a
`Resent-Message-ID` to fall back on, gets one generated:
`make_msgid('ARCHIVE')` in `MessageWrapper.get_msgid()` (mail.py:898). The
message is also marked with the `NO_MSGID` bit of `spam_score`, and
`created_id` is set to True. This happens on every ingestion path - the mailman
pipe (`archive-mail.py` -> `archive_message()`), the API import, and mailbox
file imports (`Loader`) - because `get_msgid()` runs from
`MessageWrapper.__init__`. No inspector rejects a message for lacking an id.

The generated value matters because `msgid` is a non-null column and because
`make_hash(msgid, listname)` produces the `hashcode`, which is both the message
URL and the blob storage key. It is also the duplicate-detection key
(`check_redelivery()`, mail.py:1091) and appears in the `ml-messages-json` blob
via `Message.as_json()`. It plays no threading role: nothing can reference an id
the archive minted after the fact.

`make_msgid()` derives its value from clock, pid and randomness, so **the same
message imported twice gets two different ids**, two different hashcodes and two
different URLs. That defeats any deduplication keyed on `msgid`.

### Three eras of the archived copy

Whether the generated id is part of the archived copy of the message depends on
when that copy was written:

| Era | Archived copy | Why |
| --- | --- | --- |
| before 2016-02-12 | no generated id | the header was not added at all |
| 2016-02-12 .. 2020-04-13 | **carries the generated id** | `3b6a7b8ca` "Save archive generated message-id in message file" added the `add_header`/`replace_header` call, and `write_msg()` at the time serialized the parsed message, `flatten_message(self.email_message)` |
| after 2020-04-13 | no generated id | `43f90b988` "Modify MessageWrapper to accept raw bytes, and save those without running through email.message" changed `write_msg()` to store `self.bytes`, the raw incoming bytes, which `__init__` snapshots *before* `get_msgid()` adds the header |

The 2020 change ended the 2016 behavior as a side effect; the comment in
`get_msgid()` claiming the header "gets to disk file" stayed behind and was
wrong for six years. It has been corrected.

Consequence of the current era: for these messages the DB row and the JSON blob
report a `Message-ID` that the archived copy, and therefore the message detail
page and any mbox export, does not contain.

The boundary is the date the *file* was written, not the date of the message.
Seen from message dates it looks like a cutoff around 2015, because the backfill
of the legacy archive up to the cutover ran inside the 2016-2020 window, while
messages arriving live after 2020 are on the raw-bytes path.

### How common, and are they spam?

Measured on the dev database, 3,580,588 messages:

- 29,617 have a generated id, 0.83%.
- `spam_score` is exactly 4 (the `NO_MSGID` mark alone) for 29,598 of them, -1
  (explicitly marked not spam) for 19, and 1000 (marked for removal) for none.
- Split by era, using "carries a References header" as a proxy for real
  conversation: outside Jun 2006 - Jun 2008, 16,597 messages of which 9,842
  (59%) have References; inside that window, 13,020 messages of which 406 (3%)
  do.

So they are two populations, a 2006-2008 spam wave and otherwise ordinary
working group mail (`namedroppers` 9,615, `pwe3` 5,322, threaded replies with
real References chains). **A missing `Message-ID` is not by itself a spam
signal**, and nothing user-facing filters on the `NO_MSGID` mark - only admin
views and the `exclude_not_spam` search parameter look at `spam_score`.

## Decision

Mailbox file imports are idempotent, and recognize an already-archived message
without relying on the generated id.

1. `Loader._is_archived()` (mail.py:682) checks `Message.msgid` when the message
   carried its own id. When `created_id` is True it instead compares the
   archived copy of the candidates that share the list and date against the
   incoming bytes.
2. `strip_generated_msgid()` (mail.py:510) removes a `*.ARCHIVE@*` `Message-ID`
   line from the header block of the archived copy before that comparison, so
   copies written in the 2016-2020 era match too.
3. An already-archived message raises `DuplicateMessage` (mail.py:130), a
   `NotArchived` subclass, counted in `Loader.stats['duplicates']` and logged as
   a warning. No copy is siloed and nothing is written.
4. Siloed writes (`_dupes`, `_filtered`, `_spam`) pass `allow_overwrite=True`
   and no longer log an error or create incremented disk copies, so re-running
   an import cannot fail on a key it wrote itself.

The comparison works because both sides are the message as it arrived: `self.bytes`
is snapshotted in `__init__` before `get_msgid()` mutates the headers.

## Consequences

- An import can be re-run over the same mailbox file, including files where
  messages lost their `Message-ID` to corruption, without archiving anything
  twice or minting new ids and URLs.
- For messages with a generated id the candidate set is bounded by list and
  date, and each candidate costs a blob read. For legacy files where many
  messages lost their ids and share a coarse date, that is more reads than the
  msgid path.
- On a mailbox import, a message reusing an archived msgid with differing
  content is now dropped with no copy kept; it used to go to
  `ml-messages-dupes` for review. The live mailman path still keeps those
  copies.
- The live path is **not** covered. A redelivery of a no-msgid message through
  mailman still mints a new id, so `check_redelivery()` cannot recognize it and
  the message is archived again under a new URL. Giving `check_redelivery()` the
  same content-based fallback is the fix if that becomes a problem.
- The byte comparison depends on the snapshot order in `MessageWrapper.__init__`.
  Moving `self.bytes` to after `get_msgid()` - which is what it would take to
  put the generated id back into the archived copy - silently breaks it: every
  no-msgid message would look new on the next import. Both changes have to
  happen in the same commit.

The invariants are pinned by tests in `tests/archive/mail.py`:
`test_Loader_process_skips_already_archived_message`,
`test_Loader_process_skips_already_archived_message_without_msgid` and
`test_Loader_process_skips_archived_copy_with_generated_msgid`. Each fails if the
corresponding branch is removed.
