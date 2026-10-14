# Same Message-ID, different content

- Status: Accepted
- Date: 2026-09-17 (design discussed 2026-08-28)
- Affects: `archive/mail.py` (`make_hash`, `content_digest`,
  `MessageWrapper.check_redelivery`, `MessageWrapper.get_hash`),
  `archive/utils.py` (`move_list`)

## Context

On rare occasions a message arrives for a list carrying the same `Message-ID`
as a message already archived on that list, but it is a different message by
content. A client bug, a mailer that reuses ids, or a resend with edits can all
produce one. Until now `check_redelivery()` compared content with
`is_duplicate_message()`, dropped a true redelivery, and otherwise wrote a copy
to `ml-messages-dupes` and raised `DuplicateMessageId`. The message never
reached the archive, browse or search.

The obstacle was structural, not the database. The hashcode is
`make_hash(msgid, listname)`, a SHA-1 of the message-id and list name, and it is
the message URL, the `ml-messages` blob key and the `ml-messages-json` blob key.
Two different messages sharing msgid and list would collide in all three.
`Message.msgid` is indexed but not unique, and `get_message_prefer_list()`
already tolerates one msgid matching several rows.

## Decision

A message that reuses a msgid on a list with different content is archived as
a distinct message, with its hashcode salted by a digest of its raw bytes.

1. `mail.content_digest()` returns a SHA-256 of the message bytes exactly as
   they arrived, which is also exactly what the archived copy stores.
2. `make_hash(msgid, listname, content_digest=None)` folds the digest into the
   SHA-1 after the list name. Without a digest the value is unchanged, so every
   existing hashcode is stable.
3. `check_redelivery()` raises `Redelivery` for a true redelivery as before.
   When the content differs it sets `MessageWrapper.content_digest` and
   returns, so `save()` continues into `check_hashcode_collision()` and the
   normal archive path. The real msgid stays in `Message.msgid`.
4. The message archived first keeps the plain hashcode. Only the newcomer is
   salted.
5. `move_list()` recomputes hashcodes for the target list. A salted message
   is recognised because its hashcode differs from `make_hash(msgid, source)`.
   For those the digest is recomputed from the stored bytes and the salt
   applied again, so the pair does not collide on the new list. This is
   possible only because the digest is over the stored bytes.
6. `DuplicateMessageId` (since renamed `UnverifiableDuplicate`) and the
   `_dupes` copy remain for one case only: an archived copy sharing the msgid
   cannot be read, so content cannot be compared. Archiving blind could turn a
   redelivery into a second message, so the copy goes to review instead.

### Why a content salt

- **Deterministic.** Re-importing the same bytes yields the same digest, the
  same hashcode and the same URL. A redelivery of the salted message with
  different bytes, an extra Received header say, is caught by
  `find_duplicate()` on content before any digest is computed, so it is
  dropped rather than given a second URL. An incremental suffix (`msgid.1`,
  `.2`) is order dependent and gives different URLs on differently ordered
  re-runs.
- **Keeps the real msgid.** Minting a fresh `ARCHIVE@` id, the `created_id`
  path, would lose the id from the database, break msgid search and any
  `References` pointing at it, and is non-deterministic besides.
- **Nothing downstream changes.** Threading, indexing, static pages, JSON blobs
  and attachments all key off the hashcode already.

### Why raw bytes and not normalised content

The first draft digested the content normalised the way `is_duplicate_message()`
compares it, so that duplicates would share a digest. That was rejected. A
hashcode is a permanent URL and blob key, and the normalisation helpers,
`strip_mailman_footer()` and friends, are working code that changes. Commit
`20f385e6b` changed footer stripping the week before this landed. A digest
that depends on them cannot be reproduced once they change, which would break
`move_list()` and any future recomputation. The raw bytes are what the archive
stores and never edits, so the digest is reproducible for the life of the
message. Redelivery detection does not need the digest to be
normalisation-aware, since it compares content first and only computes a digest
for a message it has already decided is new.

### Why the stored bytes are not annotated

Recent messages carry an `Archived-At` header predicted by Mailman, which is
wrong for the salted message. Writing the assigned URL into an `X-` header was
considered and rejected. The archived copy is the message as it arrived, byte
for byte, and the byte comparison in `find_duplicate()` and `purge_incoming()`
depends on that. The generated Message-ID episode (see
`generated_message_id.md`) is what happens when the archive edits stored
headers: era dependent byte variants that need stripping code for years
afterwards. The URL already survives a rebuild in the blob key, the `hashcode`
column and the JSON blob. `Archived-At` is left as received, like a wrong
`Date` header would be.

## Consequences

- Both messages appear in browse, search and thread views. Replies whose
  `In-Reply-To` names the shared msgid attach to whichever row
  `get_message_prefer_list()` returns first. That ambiguity is inherent to the
  input and was already accepted for cross-list msgid collisions.
- The salted rule is order dependent in one scenario: a rebuild from original
  mbox sources into an empty database and empty blob store. Whichever variant is
  processed first gets the plain hash. If that rebuild ever becomes a
  requirement, the fix is an order independent rule (salt both, or give the
  plain hash to the earlier `Date`), not annotation of stored files.
- No marker is stored on the row. A first draft set a `DUPLICATE_MSGID` bit in
  `spam_score`, at value 16, which turned out to be the bit
  `bin/corruption_identify.py` and `bin/corruption_remove.py` use to flag
  corrupted mbox regions, set on 2,321 messages in the archive. The field is
  overloaded and a positive value reads as spam by convention, see
  `docs/spam_score_info.md`. Salted status is instead derived where it is
  needed: a message is salted exactly when its hashcode is not
  `make_hash(msgid, listname)`.
- The rare path costs one extra blob read per existing message with the msgid:
  `find_duplicate()` reads them to compare, then the unreadable check reads them
  again through the cached `pymsg`.
- Messages already sitting in `ml-messages-dupes` are not backfilled by this
  change. The bucket kept their original bytes, so a one-off command can re-run
  each through `archive_message()` and they will take the salted path.

The behaviour is pinned by tests in `tests/archive/mail.py`
(`test_archive_message_duplicate_msgid_different_content`,
`test_archive_message_duplicate_msgid_variant_reimport`,
`test_archive_message_duplicate_msgid_unreadable_archived_copy`) and
`tests/archive/utils.py` (`test_move_list_keeps_content_digest`).
