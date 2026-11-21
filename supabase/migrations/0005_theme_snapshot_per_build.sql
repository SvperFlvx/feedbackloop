-- Themes are mutable by design: every regroup rewrites theme_item. That is
-- correct for the live view and fatal for history — once the AI regroups,
-- what a theme contained at the previous build is gone.
--
-- The lifecycle view (appeared, grew, went quiet, closed by a fix) needs that
-- history, and it is unreconstructable after the fact. Same argument as
-- build_audience: write it at the moment or never have it.
--
-- One row per theme per build, written when a build ships. Numerator and
-- denominator are both stored, so a past build's reach reads straight off the
-- snapshot and never shifts because membership or grouping changed later.
--
-- Applied 21 November 2026. Security advisors clean afterwards.

create table theme_snapshot (
  theme_id          uuid not null references theme (id) on delete cascade,
  build_id          uuid not null references build (id) on delete cascade,
  item_count        int not null,
  people_external   int not null,   -- how many external people this theme reached
  people_internal   int not null,
  audience_external int not null,   -- how many were invited, from build_audience
  audience_internal int not null,
  captured_at       timestamptz not null default now(),
  primary key (theme_id, build_id)
);

comment on table theme_snapshot is
  'What a theme looked like when a build shipped. No row means the theme did '
  'not exist at that build. Never updated: a snapshot is a claim about the past.';

create index theme_snapshot_build on theme_snapshot (build_id);

alter table theme_snapshot enable row level security;

-- Readable by whoever can read themes, which is owners and editors only.
-- Insert only: no update policy and no delete policy, so a shipped build's
-- snapshot cannot be rewritten.
create policy theme_snapshot_read on theme_snapshot for select
  using (exists (
    select 1 from theme t
    where t.id = theme_snapshot.theme_id and private.can_read_all(t.project_id)
  ));

create policy theme_snapshot_insert on theme_snapshot for insert
  with check (exists (
    select 1 from theme t
    where t.id = theme_snapshot.theme_id and private.can_read_all(t.project_id)
  ));
