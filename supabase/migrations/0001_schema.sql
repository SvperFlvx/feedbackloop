-- FeedbackLoop — core schema
-- Target: Postgres 15+ (Supabase). Run before 0002_rls.sql.
--
-- Three layers, deliberately separated:
--   items   are facts     — append-only, never rewritten
--   themes  are a reading — mutable, owned by the AI, revised freely
--   exports are snapshots — frozen lists of item ids, never follow a theme

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- people and organisations
-- ---------------------------------------------------------------------------

-- Mirrors auth.users. Supabase owns identity; we own everything about a person
-- that the product needs to display.
create table profile (
  id           uuid primary key references auth.users (id) on delete cascade,
  display_name text not null,
  avatar_path  text,
  created_at   timestamptz not null default now()
);

create table org (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  created_at timestamptz not null default now()
);

-- Axis one: do you belong to the owning organisation, or are you an outside guest?
-- This is separate from what you can do in any given project, and it is what
-- guarantees a client invited to one project has no path to another.
create type org_membership as enum ('internal', 'guest');

create table org_member (
  org_id     uuid not null references org (id) on delete cascade,
  person_id  uuid not null references profile (id) on delete cascade,
  membership org_membership not null,
  created_at timestamptz not null default now(),
  primary key (org_id, person_id)
);

-- ---------------------------------------------------------------------------
-- projects and roles
-- ---------------------------------------------------------------------------

create table project (
  id         uuid primary key default gen_random_uuid(),
  org_id     uuid not null references org (id) on delete cascade,
  name       text not null,
  created_at timestamptz not null default now(),
  archived_at timestamptz
);

-- Axis two: what you can do inside one project.
--   owner        billing, membership, settings, delete. Exactly one.
--   editor       sees all feedback, works themes, exports, invites.
--   collaborator gives feedback, sees only their own items.
create type project_role as enum ('owner', 'editor', 'collaborator');

create table project_member (
  project_id uuid not null references project (id) on delete cascade,
  person_id  uuid not null references profile (id) on delete cascade,
  role       project_role not null,
  invited_by uuid references profile (id),
  created_at timestamptz not null default now(),
  primary key (project_id, person_id)
);

-- Exactly one owner per project.
create unique index project_single_owner
  on project_member (project_id)
  where role = 'owner';

create index project_member_person on project_member (person_id);

-- Share links always grant 'collaborator' and never 'editor'. The role column
-- exists for readability, with a constraint that makes the rule unbreakable.
create table share_link (
  id         uuid primary key default gen_random_uuid(),
  project_id uuid not null references project (id) on delete cascade,
  token      text not null unique,
  role       project_role not null default 'collaborator',
  created_by uuid not null references profile (id),
  expires_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default now(),
  constraint share_link_collaborator_only check (role = 'collaborator')
);

-- ---------------------------------------------------------------------------
-- builds, and the attendance register
-- ---------------------------------------------------------------------------

create table build (
  id         uuid primary key default gen_random_uuid(),
  project_id uuid not null references project (id) on delete cascade,
  label      text not null,                 -- '1.8.4'
  shipped_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique (project_id, label)
);

-- THE ATTENDANCE REGISTER.
-- Written once, when a build ships: the set of people who had access at that
-- moment. Reach is always measured against this, never against today's
-- membership, so a percentage never moves because somebody joined or left.
-- This cannot be reconstructed after the fact, which is why it exists from
-- day one rather than being added when the number starts drifting.
create table build_audience (
  build_id   uuid not null references build (id) on delete cascade,
  person_id  uuid not null references profile (id) on delete cascade,
  role       project_role not null,         -- their role at ship time
  recorded_at timestamptz not null default now(),
  primary key (build_id, person_id)
);

-- ---------------------------------------------------------------------------
-- screens: a stable identity over unstable raw keys
-- ---------------------------------------------------------------------------

-- A screen is the owner's grouping. The SDK and manual uploads report a raw
-- key, which changes when engineers rename things. Items keep the raw key they
-- arrived with, forever; screens map keys to a name the owner chose. Renaming
-- or merging a screen therefore never rewrites a single item.
create table screen (
  id         uuid primary key default gen_random_uuid(),
  project_id uuid not null references project (id) on delete cascade,
  name       text not null,
  created_at timestamptz not null default now(),
  unique (project_id, name)
);

create table screen_key (
  project_id uuid not null references project (id) on delete cascade,
  raw_key    text not null,
  screen_id  uuid not null references screen (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (project_id, raw_key)
);

-- ---------------------------------------------------------------------------
-- submissions and items
-- ---------------------------------------------------------------------------

create type capture_source as enum ('sdk', 'upload', 'web');

-- What a person actually sent: one screenshot, optionally some audio, with
-- markers on it. One submission can yield several items.
create table submission (
  project_id   uuid not null references project (id) on delete cascade,
  id           uuid primary key default gen_random_uuid(),
  build_id     uuid references build (id) on delete set null,
  author_id    uuid not null references profile (id),
  source       capture_source not null,
  raw_screen_key text,
  screenshot_path text,                     -- object storage path, not a URL
  audio_path   text,
  created_at   timestamptz not null default now()
);

create index submission_project_created on submission (project_id, created_at desc);

create table marker (
  id            uuid primary key default gen_random_uuid(),
  submission_id uuid not null references submission (id) on delete cascade,
  x             numeric(6,4) not null,      -- 0..1, fraction of image width
  y             numeric(6,4) not null,      -- 0..1, fraction of image height
  ordinal       int not null
);

create type item_type as enum ('bug', 'question', 'improvement', 'praise');

-- An item is a fact: this person said this thing, about this screen, on this
-- build. Items are append-only. A correction is a new item, never an edit.
create table item (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null references project (id) on delete cascade,
  submission_id  uuid references submission (id) on delete set null,
  marker_id      uuid references marker (id) on delete set null,
  build_id       uuid references build (id) on delete set null,
  author_id      uuid not null references profile (id),
  raw_screen_key text,
  type           item_type not null,
  body           text not null,             -- transcript or typed text
  created_at     timestamptz not null default now()
);

create index item_project_created on item (project_id, created_at desc);
create index item_project_author  on item (project_id, author_id);
create index item_build           on item (build_id);
create index item_raw_key         on item (project_id, raw_screen_key);

-- ---------------------------------------------------------------------------
-- themes: the mutable reading
-- ---------------------------------------------------------------------------

create table theme (
  id               uuid primary key default gen_random_uuid(),
  project_id       uuid not null references project (id) on delete cascade,
  name             text not null,
  summary          text,
  -- Colour follows the theme, never its rank. Assigned once, persisted here.
  categorical_slot smallint not null check (categorical_slot between 1 and 8),
  created_at       timestamptz not null default now(),
  retired_at       timestamptz                -- split or merged away
);

create table theme_item (
  theme_id   uuid not null references theme (id) on delete cascade,
  item_id    uuid not null references item (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (theme_id, item_id)
);

create index theme_item_item on theme_item (item_id);

create type principle_strength as enum ('strong', 'strong_on_pattern', 'provisional');

create table principle (
  id         uuid primary key default gen_random_uuid(),
  project_id uuid not null references project (id) on delete cascade,
  name       text not null,
  strength   principle_strength not null,
  created_at timestamptz not null default now()
);

create table principle_theme (
  principle_id uuid not null references principle (id) on delete cascade,
  theme_id     uuid not null references theme (id) on delete cascade,
  primary key (principle_id, theme_id)
);

-- ---------------------------------------------------------------------------
-- exports: frozen snapshots
-- ---------------------------------------------------------------------------

create type export_target as enum ('jira', 'productboard', 'github', 'webhook', 'csv');

create table export (
  id          uuid primary key default gen_random_uuid(),
  project_id  uuid not null references project (id) on delete cascade,
  theme_id    uuid references theme (id) on delete set null,
  target      export_target not null,
  external_ref text,                        -- the ticket or note it became
  created_by  uuid not null references profile (id),
  created_at  timestamptz not null default now()
);

-- The frozen list. If the theme later splits, this does not change — the
-- export recorded what was true when it left.
create table export_item (
  export_id uuid not null references export (id) on delete cascade,
  item_id   uuid not null references item (id) on delete cascade,
  primary key (export_id, item_id)
);

-- ---------------------------------------------------------------------------
-- verification: one bundle per person per build
-- ---------------------------------------------------------------------------

create type verification_answer as enum ('fixed', 'not_fixed', 'not_sure');

create table verification_request (
  id         uuid primary key default gen_random_uuid(),
  build_id   uuid not null references build (id) on delete cascade,
  person_id  uuid not null references profile (id) on delete cascade,
  sent_at    timestamptz,
  created_at timestamptz not null default now(),
  -- One request per person per build. Not one per item, and not one per marker.
  unique (build_id, person_id)
);

create table verification_response (
  request_id uuid not null references verification_request (id) on delete cascade,
  item_id    uuid not null references item (id) on delete cascade,
  answer     verification_answer not null,
  note       text,
  created_at timestamptz not null default now(),
  primary key (request_id, item_id)
);
