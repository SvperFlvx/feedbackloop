# FeedbackLoop — backend

Database schema, access control, and the evaluation harness for the AI layer.

Non-technical stakeholders annotate a screenshot of a pre-release build and
leave a voice note. The owner gets it grouped into themes, mapped to screens,
and interpreted into design principles. The claim this product can make and
others cannot: **which screen it broke on, and whether it is still broken in
the current build.**

Product decisions, with reasoning, live in the build tracker rather than here.
Read that before changing anything structural.

## Repositories

| Repo | Visibility | Holds |
| --- | --- | --- |
| `feedbackloop` (this one) | private | schema, access control, server, eval harness |
| `feedbackloop-ios` | private | the iOS app and the App Clip |
| `feedbackloop-sdk` | **public** | the Swift package customers embed |
| `feedbackloop-site` | private | marketing site and waitlist |

Only the SDK must be public — SwiftPM resolves against a Git URL, so that
repository *is* the distribution channel. The backend must never be. The other
three get created when there is something to put in them, not before.

## Setup

```bash
cp .env.example .env     # then fill it in. .env is gitignored and stays that way
```

Run the migrations against the Supabase project in order:

```bash
psql "$DATABASE_URL" -f supabase/migrations/0001_schema.sql
psql "$DATABASE_URL" -f supabase/migrations/0002_rls.sql
```

`0001` creates the tables. `0002` creates every rule about who can see what.

## The one thing to understand before changing anything

**Access rules live in the database, not in application code.** If they lived in
app code they would have to be written correctly in the iOS app, the web view,
the SDK, every background job and every one-off script — and missing one leaks
one client's unreleased product to another. In Postgres the rule applies to the
query itself and there is no path around it.

Three consequences that look like bugs and are not:

- **Items cannot be updated or deleted.** Those commands have no policy, and
  with row-level security on, no policy means denied for everyone. A correction
  is a new row. Items are facts.
- **Exports cannot be changed either.** An export records what was true when it
  left. An editable record of the past is not a record.
- **`build_audience` is written once, when a build ships.** It is the register of
  who had access at that moment, and reach percentages are measured against it.
  It cannot be reconstructed afterwards, which is the whole reason it exists.

A plain-language walkthrough of every schema decision, written for someone who
does not read SQL, is in the project docs.

## Before real customer data

`supabase/migrations/0002_rls.sql` has not been reviewed by anyone who did not
write it. A leak between two clients would expose one company's unreleased
product to another, and that class of mistake looks fine in testing because the
builder is the only user. That review happens before the first real client
screenshot, not after.

## Evaluation harness

`eval/` scores how well a model groups feedback into themes, against a fixed set
with a known-correct grouping. See `eval/README.md`.

The number that matters: a free group-by-screen baseline scores **V-measure
0.573**. Any paid model that cannot clearly beat that is not worth paying for.
