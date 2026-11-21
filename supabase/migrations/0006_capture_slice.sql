-- Capture slice: a test instrument, not the product.
--
-- WHY THIS IS SEPARATE FROM submission
--
-- submission.author_id is NOT NULL against profile, and profile.id references
-- auth.users. A capture link has no account behind it, so writing test data
-- into submission would mean one of two things: creating real auth users for
-- G's colleagues, or making author_id nullable and loosening the RLS that
-- depends on it. The second weakens a production constraint to accommodate a
-- test, which is how a test instrument quietly becomes a hole in the product.
--
-- So the slice writes here instead, and the results are translated into items
-- by hand for grouping. These two tables and two functions are expected to be
-- DROPPED once the test has answered its question. Nothing in the product
-- should come to depend on them.
--
-- THE SECURITY MODEL, STATED PLAINLY
--
-- The anon key sits in a published web page, so it is public. It is granted
-- nothing here: both tables have RLS on and no policy, which denies everyone
-- including anon. The only door is two SECURITY DEFINER functions that take a
-- token and validate it themselves. That makes the token the whole boundary,
-- and these two functions the only place it is checked.
--
-- A leaked link lets a stranger add notes to ONE project. It never lets them
-- read anyone's notes, see who else was invited, or reach any other project.
-- Tokens are stored hashed, expire, and can be revoked one person at a time.
--
-- Audio is stored in the row rather than in object storage. That is wrong for
-- the product and right for eight people: it avoids granting the public anon
-- key any write access to a storage bucket, which would be a second boundary
-- to get right for no benefit at this size. The product uses object storage
-- with signed, expiring URLs — already a row in the build plan.

-- EXPECTED ADVISOR WARNINGS. Supabase's linter reports three things about
-- this migration, and all three are deliberate. Do not "fix" them: each fix
-- breaks the capture page.
--   rls_enabled_no_policy on capture_person and capture_note -- that IS the
--     deny-all. RLS on with no policy denies every role.
--   anon and authenticated can execute the two SECURITY DEFINER functions --
--     they are the public HTTP endpoints the page calls. That is the design,
--     and the token inside them is the boundary.
-- What would be a real finding: a third function appearing in public, or a
-- policy appearing on either capture table.

create extension if not exists pgcrypto with schema extensions;

-- One row per invited person per project. The label is how they appear in the
-- results; no email, no account, nothing that needs verifying.
create table capture_person (
  id          uuid primary key default gen_random_uuid(),
  project_id  uuid not null references project (id) on delete cascade,
  label       text not null,
  affiliation participant_affiliation not null default 'internal',
  job_function participant_function,
  token_sha   text not null unique,         -- sha256 hex of the link token
  expires_at  timestamptz not null default (now() + interval '14 days'),
  revoked_at  timestamptz,
  note_cap    int not null default 50,      -- a valid token cannot flood
  created_at  timestamptz not null default now()
);

comment on table capture_person is
  'Capture-slice test instrument. One invited person per personalised link. Drop with the slice.';

-- One row per recording. screen_name is free text rather than a reference to
-- screen, because the slice shows a fixed set of prototype frames and the
-- screen table belongs to the product's own identity model.
create table capture_note (
  id                uuid primary key default gen_random_uuid(),
  capture_person_id uuid not null references capture_person (id) on delete cascade,
  screen_name       text not null,
  marker_x          numeric(6,4),           -- 0..1 fraction of image width
  marker_y          numeric(6,4),           -- 0..1 fraction of image height
  audio             bytea,                  -- null when the person typed instead
  audio_mime        text,
  transcript        text,                   -- as corrected by the person, if they did
  transcript_raw    text,                   -- as the provider returned it, for comparison
  typed             boolean not null default false,
  created_at        timestamptz not null default now(),
  constraint capture_note_has_content
    check (audio is not null or coalesce(trim(transcript), '') <> ''),
  constraint capture_note_marker_pair
    check ((marker_x is null) = (marker_y is null)),
  constraint capture_note_marker_range
    check (marker_x is null or (marker_x between 0 and 1 and marker_y between 0 and 1))
);

comment on table capture_note is
  'Capture-slice test instrument. Audio lives in the row deliberately; see 0006 header. Drop with the slice.';

create index capture_note_person on capture_note (capture_person_id);

-- RLS on, no policies: denied for everyone, anon included. The functions below
-- are SECURITY DEFINER and are the only way in.
alter table capture_person enable row level security;
alter table capture_note   enable row level security;

-- Resolve a token to a person, or raise. One place, so the rules cannot drift
-- apart between the two callers.
create or replace function private.capture_person_for(p_token text)
returns public.capture_person
language plpgsql stable security definer set search_path = '' as $$
declare
  found public.capture_person;
begin
  if p_token is null or length(p_token) < 16 then
    raise exception 'invalid link';
  end if;

  select * into found from public.capture_person
  where token_sha = encode(extensions.digest(p_token, 'sha256'), 'hex');

  if found.id is null then
    raise exception 'invalid link';
  end if;
  if found.revoked_at is not null then
    raise exception 'this link has been revoked';
  end if;
  if found.expires_at < now() then
    raise exception 'this link has expired';
  end if;

  return found;
end;
$$;

-- Deliberately in public, because it IS the HTTP endpoint the page calls.
-- Everything it returns is already known to whoever holds the link: their own
-- name and the screens they were asked to look at.
create or replace function public.capture_open(p_token text)
returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare
  who public.capture_person;
begin
  who := private.capture_person_for(p_token);
  return jsonb_build_object(
    'label', who.label,
    'project_id', who.project_id,
    'notes_so_far', (select count(*) from public.capture_note n
                     where n.capture_person_id = who.id),
    'screens', coalesce((
      select jsonb_agg(s.name order by s.name)
      from public.screen s where s.project_id = who.project_id), '[]'::jsonb)
  );
end;
$$;

-- The one write. Validates the token, caps the size and the count, and inserts.
-- Audio arrives base64 because it comes over JSON; 2 MB decoded is about four
-- minutes of speech at the bitrate a phone browser produces.
create or replace function public.capture_submit(
  p_token      text,
  p_screen     text,
  p_marker_x   numeric default null,
  p_marker_y   numeric default null,
  p_audio_b64  text    default null,
  p_audio_mime text    default null,
  p_transcript text    default null,
  p_typed      boolean default false)
returns uuid
language plpgsql volatile security definer set search_path = '' as $$
declare
  who   public.capture_person;
  blob  bytea;
  made  uuid;
begin
  who := private.capture_person_for(p_token);

  if coalesce(trim(p_screen), '') = '' then
    raise exception 'which screen is this about?';
  end if;

  if (select count(*) from public.capture_note n
      where n.capture_person_id = who.id) >= who.note_cap then
    raise exception 'this link has reached its limit of % notes', who.note_cap;
  end if;

  if p_audio_b64 is not null then
    if length(p_audio_b64) > 2800000 then   -- ~2 MB once decoded
      raise exception 'that recording is too long';
    end if;
    blob := decode(p_audio_b64, 'base64');
  end if;

  insert into public.capture_note (
    capture_person_id, screen_name, marker_x, marker_y,
    audio, audio_mime, transcript, typed)
  values (
    who.id, trim(p_screen), p_marker_x, p_marker_y,
    blob, p_audio_mime, nullif(trim(coalesce(p_transcript, '')), ''), p_typed)
  returning id into made;

  return made;
end;
$$;

-- The page calls these two and nothing else.
grant execute on function public.capture_open(text)   to anon, authenticated;
grant execute on function public.capture_submit(text, text, numeric, numeric, text, text, text, boolean)
  to anon, authenticated;

-- private.capture_person_for stays unreachable over HTTP: it is in a schema
-- PostgREST does not serve, and nothing is granted on it.
revoke all on function private.capture_person_for(text) from anon, authenticated;
