-- Two problems, both found by testing rather than by the advisors, because
-- neither is a vulnerability the advisors look for.
--
-- ONE: no role had SELECT, INSERT, UPDATE or DELETE on any table in public.
-- The grant string read anon=Dxtm / authenticated=Dxtm -- TRUNCATE,
-- REFERENCES, TRIGGER, MAINTAIN and nothing else. RLS filters rows; it does
-- not grant access to a table. So all 37 policies were unreachable and the
-- first real query the app ever made would have failed with "permission
-- denied for table", which looks nothing like its cause.
--
-- TWO: anon held TRUNCATE on every table. TRUNCATE bypasses RLS. Not
-- reachable through PostgREST, so not a live breach, but a public key should
-- not carry a standing ability to empty a table while waiting for some future
-- feature to expose it.
--
-- The shape of the fix follows a decision already settled: access rules live
-- in Postgres, so authenticated gets the DML and the policies decide what it
-- can actually see. anon gets nothing at all on any table -- the capture path
-- reaches the database only through the two SECURITY DEFINER functions in
-- 0006, which is the whole point of them being functions.
--
-- NOTE FOR WHOEVER ADDS THE NEXT TABLE: no default privileges are being set
-- here, deliberately, because a blanket default is what produced the anon
-- TRUNCATE. A new table needs its grant written explicitly, next to its RLS.

revoke all on all tables in schema public from anon;

revoke all on all tables in schema public from authenticated;
grant select, insert, update, delete on all tables in schema public to authenticated;

-- The capture-slice tables stay closed to everyone. They have RLS on and zero
-- policies by design, but a grant plus zero policies is a denial that depends
-- on nobody adding a policy later; no grant is a denial that does not.
revoke all on table capture_person from authenticated;
revoke all on table capture_note   from authenticated;

-- service_role is the server-side key and bypasses RLS by design. It keeps
-- what it has; nothing here widens it.
