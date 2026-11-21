-- Who someone works for, and what they do. Two questions, two closed lists.
--
-- Affiliation is the dogfooding axis: it drives the exclude-internal filter and
-- the "84% of this build's feedback came from your own team" line. Closed, not
-- free text, because a fixed vocabulary is the only version that stays
-- comparable across customers — "support reports different things than
-- engineering does" is only answerable if nobody invented their own words.
--
-- Function is optional. 'other' is deliberate: if it gets picked often, that is
-- the evidence for which value to add, rather than guessing now.
--
-- Applied 21 November 2026. Security advisors clean afterwards.

create type participant_affiliation as enum ('internal', 'external');

create type participant_function as enum (
  'engineering', 'design', 'product', 'sales', 'support', 'leadership', 'other'
);

alter table project_member
  add column affiliation participant_affiliation not null default 'external',
  add column job_function participant_function;

comment on column project_member.affiliation is
  'Internal = the project owner''s own organisation. Defaults to external, '
  'because anyone arriving through a share link is almost never on the team. '
  'The application sets internal explicitly for the owner at project creation.';

comment on column project_member.job_function is
  'Optional. Design matters here more than it looks: designers have the most '
  'contaminated view of the thing they designed, which is what the '
  'exclude-internal filter exists to separate out.';

-- The attendance register freezes affiliation for the same reason it freezes
-- role. Reach is now reported split by affiliation, so if someone moved from
-- external to internal, the split for an already-shipped build would otherwise
-- silently change. Past membership is unrecoverable; past affiliation is too.
alter table build_audience
  add column affiliation participant_affiliation not null default 'external';

comment on column build_audience.affiliation is
  'Their affiliation when this build shipped, not their affiliation now.';
