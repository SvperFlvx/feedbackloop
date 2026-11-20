-- FeedbackLoop — row-level security
-- Run after 0001_schema.sql.
--
-- Every rule that decides who can see what lives here, in the database.
-- None of it is enforced in application code. The reason is specific: a leak
-- between two clients exposes one company's unreleased product to another, and
-- that class of mistake looks fine in testing, because in testing you are the
-- only user. A policy in Postgres applies to every query from every surface —
-- the iOS app, the web view, the SDK, a script someone writes in a year.

-- ---------------------------------------------------------------------------
-- helpers
-- ---------------------------------------------------------------------------

create or replace function current_person() returns uuid
language sql stable as $$
  select auth.uid();
$$;

create or replace function has_project_role(p uuid, roles project_role[])
returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from project_member m
    where m.project_id = p
      and m.person_id = auth.uid()
      and m.role = any (roles)
  );
$$;

-- Sees everything in the project: owner or editor.
create or replace function can_read_all(p uuid) returns boolean
language sql stable as $$
  select has_project_role(p, array['owner','editor']::project_role[]);
$$;

-- Belongs to the project in any capacity.
create or replace function is_member(p uuid) returns boolean
language sql stable as $$
  select has_project_role(p, array['owner','editor','collaborator']::project_role[]);
$$;

-- ---------------------------------------------------------------------------
-- enable RLS everywhere, then grant back deliberately
-- ---------------------------------------------------------------------------

alter table profile               enable row level security;
alter table org                   enable row level security;
alter table org_member            enable row level security;
alter table project               enable row level security;
alter table project_member        enable row level security;
alter table share_link            enable row level security;
alter table build                 enable row level security;
alter table build_audience        enable row level security;
alter table screen                enable row level security;
alter table screen_key            enable row level security;
alter table submission            enable row level security;
alter table marker                enable row level security;
alter table item                  enable row level security;
alter table theme                 enable row level security;
alter table theme_item            enable row level security;
alter table principle             enable row level security;
alter table principle_theme       enable row level security;
alter table export                enable row level security;
alter table export_item           enable row level security;
alter table verification_request  enable row level security;
alter table verification_response enable row level security;

-- ---------------------------------------------------------------------------
-- projects and membership
-- ---------------------------------------------------------------------------

create policy project_read on project for select
  using (is_member(id));

create policy project_write on project for update
  using (has_project_role(id, array['owner']::project_role[]));

create policy member_read on project_member for select
  using (is_member(project_id));

create policy member_manage on project_member for all
  using (has_project_role(project_id, array['owner','editor']::project_role[]))
  with check (has_project_role(project_id, array['owner','editor']::project_role[]));

-- A person can always read their own profile; anyone sharing a project can
-- read a display name, because attribution is the point of the product.
create policy profile_read on profile for select
  using (
    id = current_person()
    or exists (
      select 1
      from project_member mine
      join project_member theirs on theirs.project_id = mine.project_id
      where mine.person_id = current_person()
        and theirs.person_id = profile.id
    )
  );

-- ---------------------------------------------------------------------------
-- the central rule: a collaborator sees only their own items
-- ---------------------------------------------------------------------------

create policy item_read on item for select
  using (
    can_read_all(project_id)
    or (is_member(project_id) and author_id = current_person())
  );

-- Anyone in the project may add an item, but only as themselves.
create policy item_insert on item for insert
  with check (is_member(project_id) and author_id = current_person());

-- No update policy and no delete policy, on purpose. Items are facts.
-- With RLS on and no policy for a command, that command is refused for
-- everyone. A correction is a new row.

create policy submission_read on submission for select
  using (
    can_read_all(project_id)
    or (is_member(project_id) and author_id = current_person())
  );

create policy submission_insert on submission for insert
  with check (is_member(project_id) and author_id = current_person());

create policy marker_read on marker for select
  using (exists (
    select 1 from submission s
    where s.id = marker.submission_id
      and (can_read_all(s.project_id)
           or (is_member(s.project_id) and s.author_id = current_person()))
  ));

create policy marker_insert on marker for insert
  with check (exists (
    select 1 from submission s
    where s.id = marker.submission_id
      and s.author_id = current_person()
  ));

-- ---------------------------------------------------------------------------
-- the interpretation layer: owners and editors only
-- ---------------------------------------------------------------------------
-- A collaborator never sees themes or principles. They are a reading of
-- everyone's feedback, and a collaborator cannot see everyone's feedback.

create policy theme_read on theme for select
  using (can_read_all(project_id));

create policy theme_write on theme for all
  using (can_read_all(project_id))
  with check (can_read_all(project_id));

create policy theme_item_read on theme_item for select
  using (exists (select 1 from theme t where t.id = theme_item.theme_id and can_read_all(t.project_id)));

create policy theme_item_write on theme_item for all
  using (exists (select 1 from theme t where t.id = theme_item.theme_id and can_read_all(t.project_id)))
  with check (exists (select 1 from theme t where t.id = theme_item.theme_id and can_read_all(t.project_id)));

create policy principle_read on principle for select
  using (can_read_all(project_id));

create policy principle_write on principle for all
  using (can_read_all(project_id))
  with check (can_read_all(project_id));

create policy principle_theme_rw on principle_theme for all
  using (exists (select 1 from principle p where p.id = principle_theme.principle_id and can_read_all(p.project_id)))
  with check (exists (select 1 from principle p where p.id = principle_theme.principle_id and can_read_all(p.project_id)));

-- ---------------------------------------------------------------------------
-- screens, builds, attendance
-- ---------------------------------------------------------------------------

create policy screen_read on screen for select using (is_member(project_id));
create policy screen_write on screen for all
  using (can_read_all(project_id)) with check (can_read_all(project_id));

create policy screen_key_read on screen_key for select using (is_member(project_id));
create policy screen_key_write on screen_key for all
  using (can_read_all(project_id)) with check (can_read_all(project_id));

create policy build_read on build for select using (is_member(project_id));
create policy build_write on build for all
  using (can_read_all(project_id)) with check (can_read_all(project_id));

-- The register is readable by owners and editors, because reach is their
-- number. It has no update or delete policy: attendance, once taken, stands.
create policy audience_read on build_audience for select
  using (exists (select 1 from build b where b.id = build_audience.build_id and can_read_all(b.project_id)));

create policy audience_insert on build_audience for insert
  with check (exists (select 1 from build b where b.id = build_audience.build_id and can_read_all(b.project_id)));

-- ---------------------------------------------------------------------------
-- exports and verification
-- ---------------------------------------------------------------------------

create policy export_read on export for select using (can_read_all(project_id));
create policy export_insert on export for insert with check (can_read_all(project_id));

-- No update, no delete: an export records what was true when it left.
create policy export_item_read on export_item for select
  using (exists (select 1 from export e where e.id = export_item.export_id and can_read_all(e.project_id)));

create policy export_item_insert on export_item for insert
  with check (exists (select 1 from export e where e.id = export_item.export_id and can_read_all(e.project_id)));

-- A person sees their own verification request; owners and editors see all.
create policy verification_read on verification_request for select
  using (
    person_id = current_person()
    or exists (select 1 from build b where b.id = verification_request.build_id and can_read_all(b.project_id))
  );

create policy verification_manage on verification_request for all
  using (exists (select 1 from build b where b.id = verification_request.build_id and can_read_all(b.project_id)))
  with check (exists (select 1 from build b where b.id = verification_request.build_id and can_read_all(b.project_id)));

create policy response_read on verification_response for select
  using (exists (
    select 1 from verification_request r
    join build b on b.id = r.build_id
    where r.id = verification_response.request_id
      and (r.person_id = current_person() or can_read_all(b.project_id))
  ));

create policy response_insert on verification_response for insert
  with check (exists (
    select 1 from verification_request r
    where r.id = verification_response.request_id
      and r.person_id = current_person()
  ));

-- ---------------------------------------------------------------------------
-- share links
-- ---------------------------------------------------------------------------
-- Readable only by owners and editors. Redeeming a link happens in a server
-- function that looks it up by token with elevated rights, checks expiry and
-- revocation, and inserts a collaborator row. A link is never readable by
-- someone who merely holds the token.

create policy share_link_manage on share_link for all
  using (can_read_all(project_id)) with check (can_read_all(project_id));

-- ---------------------------------------------------------------------------
-- org tables
-- ---------------------------------------------------------------------------

create policy org_read on org for select
  using (exists (select 1 from org_member m where m.org_id = org.id and m.person_id = current_person()));

create policy org_member_read on org_member for select
  using (exists (select 1 from org_member m where m.org_id = org_member.org_id and m.person_id = current_person()));
