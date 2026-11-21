-- Postgres grants EXECUTE on every new function to PUBLIC by default, so
-- "revoke ... from anon" in 0006 removed a named grant while leaving the
-- blanket one in place. Testing caught it: anon could still call
-- private.capture_person_for. Not reachable over HTTP, because PostgREST does
-- not serve the private schema -- but it is the same class of mistake 0003 was
-- written to fix, and least privilege should not depend on a schema staying
-- unexposed.
--
-- The explicit grants to authenticated stay. RLS policy expressions are
-- evaluated as the calling role, and the four policy helpers are what every
-- policy calls, so revoking those would deny real users their own rows.
-- Revoking from PUBLIC leaves the named grants untouched.

revoke execute on function private.can_read_all(uuid)                        from public;
revoke execute on function private.current_person()                          from public;
revoke execute on function private.is_member(uuid)                           from public;
revoke execute on function private.has_project_role(uuid, public.project_role[]) from public;
revoke execute on function private.capture_person_for(text)                  from public;

-- capture_person_for is called only by the two public wrappers, which are
-- SECURITY DEFINER and run as their owner. Nothing else needs to reach it.
revoke execute on function private.capture_person_for(text) from anon, authenticated, service_role;
