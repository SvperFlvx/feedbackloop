-- The access-control helpers were in `public`, which PostgREST exposes. That
-- published has_project_role at /rest/v1/rpc/has_project_role, callable by
-- anyone. Today it only reports on the caller's own memberships, but it is
-- SECURITY DEFINER, so it reads project_member with RLS bypassed. A future
-- edit that loosened its WHERE clause would turn a public URL into a full
-- membership oracle. Moving the helpers to a schema PostgREST does not serve
-- removes the endpoint while leaving the policies working.
--
-- Also sets search_path on every helper, so none of them can be influenced by
-- objects created in a schema earlier in a caller's path.
--
-- Applied 20 November 2026. Supabase security advisors clean afterwards.

create schema if not exists private;

grant usage on schema private to authenticated, anon, service_role;

create or replace function private.current_person() returns uuid
language sql stable set search_path = '' as $$
  select auth.uid();
$$;

create or replace function private.has_project_role(p uuid, roles public.project_role[])
returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.project_member m
    where m.project_id = p
      and m.person_id = auth.uid()
      and m.role = any (roles)
  );
$$;

create or replace function private.can_read_all(p uuid) returns boolean
language sql stable set search_path = '' as $$
  select private.has_project_role(p, array['owner','editor']::public.project_role[]);
$$;

create or replace function private.is_member(p uuid) returns boolean
language sql stable set search_path = '' as $$
  select private.has_project_role(p, array['owner','editor','collaborator']::public.project_role[]);
$$;

grant execute on all functions in schema private to authenticated, anon, service_role;

-- Policies hold the function by identity, so they must go before the old
-- functions can be dropped. Every policy below is recreated unchanged apart
-- from the private.* prefix — see 0002 for the reasoning behind each one.

drop policy if exists project_read on project;
drop policy if exists project_write on project;
drop policy if exists member_read on project_member;
drop policy if exists member_manage on project_member;
drop policy if exists profile_read on profile;
drop policy if exists item_read on item;
drop policy if exists item_insert on item;
drop policy if exists submission_read on submission;
drop policy if exists submission_insert on submission;
drop policy if exists marker_read on marker;
drop policy if exists marker_insert on marker;
drop policy if exists theme_read on theme;
drop policy if exists theme_write on theme;
drop policy if exists theme_item_read on theme_item;
drop policy if exists theme_item_write on theme_item;
drop policy if exists principle_read on principle;
drop policy if exists principle_write on principle;
drop policy if exists principle_theme_rw on principle_theme;
drop policy if exists screen_read on screen;
drop policy if exists screen_write on screen;
drop policy if exists screen_key_read on screen_key;
drop policy if exists screen_key_write on screen_key;
drop policy if exists build_read on build;
drop policy if exists build_write on build;
drop policy if exists audience_read on build_audience;
drop policy if exists audience_insert on build_audience;
drop policy if exists export_read on export;
drop policy if exists export_insert on export;
drop policy if exists export_item_read on export_item;
drop policy if exists export_item_insert on export_item;
drop policy if exists verification_read on verification_request;
drop policy if exists verification_manage on verification_request;
drop policy if exists response_read on verification_response;
drop policy if exists response_insert on verification_response;
drop policy if exists share_link_manage on share_link;
drop policy if exists org_read on org;
drop policy if exists org_member_read on org_member;

drop function if exists public.can_read_all(uuid);
drop function if exists public.is_member(uuid);
drop function if exists public.has_project_role(uuid, public.project_role[]);
drop function if exists public.current_person();

create policy project_read on project for select
  using (private.is_member(id));

create policy project_write on project for update
  using (private.has_project_role(id, array['owner']::project_role[]));

create policy member_read on project_member for select
  using (private.is_member(project_id));

create policy member_manage on project_member for all
  using (private.has_project_role(project_id, array['owner','editor']::project_role[]))
  with check (private.has_project_role(project_id, array['owner','editor']::project_role[]));

-- A person can always read their own profile; anyone sharing a project can
-- read a display name, because attribution is the point of the product.
create policy profile_read on profile for select
  using (
    id = private.current_person()
    or exists (
      select 1
      from project_member mine
      join project_member theirs on theirs.project_id = mine.project_id
      where mine.person_id = private.current_person()
        and theirs.person_id = profile.id
    )
  );

-- ---------------------------------------------------------------------------
-- the central rule: a collaborator sees only their own items
-- ---------------------------------------------------------------------------

create policy item_read on item for select
  using (
    private.can_read_all(project_id)
    or (private.is_member(project_id) and author_id = private.current_person())
  );

-- Anyone in the project may add an item, but only as themselves.
create policy item_insert on item for insert
  with check (private.is_member(project_id) and author_id = private.current_person());

-- No update policy and no delete policy, on purpose. Items are facts.
-- With RLS on and no policy for a command, that command is refused for
-- everyone. A correction is a new row.

create policy submission_read on submission for select
  using (
    private.can_read_all(project_id)
    or (private.is_member(project_id) and author_id = private.current_person())
  );

create policy submission_insert on submission for insert
  with check (private.is_member(project_id) and author_id = private.current_person());

create policy marker_read on marker for select
  using (exists (
    select 1 from submission s
    where s.id = marker.submission_id
      and (private.can_read_all(s.project_id)
           or (private.is_member(s.project_id) and s.author_id = private.current_person()))
  ));

create policy marker_insert on marker for insert
  with check (exists (
    select 1 from submission s
    where s.id = marker.submission_id
      and s.author_id = private.current_person()
  ));

-- ---------------------------------------------------------------------------
-- the interpretation layer: owners and editors only
-- ---------------------------------------------------------------------------
-- A collaborator never sees themes or principles. They are a reading of
-- everyone's feedback, and a collaborator cannot see everyone's feedback.

create policy theme_read on theme for select
  using (private.can_read_all(project_id));

create policy theme_write on theme for all
  using (private.can_read_all(project_id))
  with check (private.can_read_all(project_id));

create policy theme_item_read on theme_item for select
  using (exists (select 1 from theme t where t.id = theme_item.theme_id and private.can_read_all(t.project_id)));

create policy theme_item_write on theme_item for all
  using (exists (select 1 from theme t where t.id = theme_item.theme_id and private.can_read_all(t.project_id)))
  with check (exists (select 1 from theme t where t.id = theme_item.theme_id and private.can_read_all(t.project_id)));

create policy principle_read on principle for select
  using (private.can_read_all(project_id));

create policy principle_write on principle for all
  using (private.can_read_all(project_id))
  with check (private.can_read_all(project_id));

create policy principle_theme_rw on principle_theme for all
  using (exists (select 1 from principle p where p.id = principle_theme.principle_id and private.can_read_all(p.project_id)))
  with check (exists (select 1 from principle p where p.id = principle_theme.principle_id and private.can_read_all(p.project_id)));

-- ---------------------------------------------------------------------------
-- screens, builds, attendance
-- ---------------------------------------------------------------------------

create policy screen_read on screen for select using (private.is_member(project_id));
create policy screen_write on screen for all
  using (private.can_read_all(project_id)) with check (private.can_read_all(project_id));

create policy screen_key_read on screen_key for select using (private.is_member(project_id));
create policy screen_key_write on screen_key for all
  using (private.can_read_all(project_id)) with check (private.can_read_all(project_id));

create policy build_read on build for select using (private.is_member(project_id));
create policy build_write on build for all
  using (private.can_read_all(project_id)) with check (private.can_read_all(project_id));

-- The register is readable by owners and editors, because reach is their
-- number. It has no update or delete policy: attendance, once taken, stands.
create policy audience_read on build_audience for select
  using (exists (select 1 from build b where b.id = build_audience.build_id and private.can_read_all(b.project_id)));

create policy audience_insert on build_audience for insert
  with check (exists (select 1 from build b where b.id = build_audience.build_id and private.can_read_all(b.project_id)));

-- ---------------------------------------------------------------------------
-- exports and verification
-- ---------------------------------------------------------------------------

create policy export_read on export for select using (private.can_read_all(project_id));
create policy export_insert on export for insert with check (private.can_read_all(project_id));

-- No update, no delete: an export records what was true when it left.
create policy export_item_read on export_item for select
  using (exists (select 1 from export e where e.id = export_item.export_id and private.can_read_all(e.project_id)));

create policy export_item_insert on export_item for insert
  with check (exists (select 1 from export e where e.id = export_item.export_id and private.can_read_all(e.project_id)));

-- A person sees their own verification request; owners and editors see all.
create policy verification_read on verification_request for select
  using (
    person_id = private.current_person()
    or exists (select 1 from build b where b.id = verification_request.build_id and private.can_read_all(b.project_id))
  );

create policy verification_manage on verification_request for all
  using (exists (select 1 from build b where b.id = verification_request.build_id and private.can_read_all(b.project_id)))
  with check (exists (select 1 from build b where b.id = verification_request.build_id and private.can_read_all(b.project_id)));

create policy response_read on verification_response for select
  using (exists (
    select 1 from verification_request r
    join build b on b.id = r.build_id
    where r.id = verification_response.request_id
      and (r.person_id = private.current_person() or private.can_read_all(b.project_id))
  ));

create policy response_insert on verification_response for insert
  with check (exists (
    select 1 from verification_request r
    where r.id = verification_response.request_id
      and r.person_id = private.current_person()
  ));

-- ---------------------------------------------------------------------------
-- share links
-- ---------------------------------------------------------------------------
-- Readable only by owners and editors. Redeeming a link happens in a server
-- function that looks it up by token with elevated rights, checks expiry and
-- revocation, and inserts a collaborator row. A link is never readable by
-- someone who merely holds the token.

create policy share_link_manage on share_link for all
  using (private.can_read_all(project_id)) with check (private.can_read_all(project_id));

-- ---------------------------------------------------------------------------
-- org tables
-- ---------------------------------------------------------------------------

create policy org_read on org for select
  using (exists (select 1 from org_member m where m.org_id = org.id and m.person_id = private.current_person()));

create policy org_member_read on org_member for select
  using (exists (select 1 from org_member m where m.org_id = org_member.org_id and m.person_id = private.current_person()));
