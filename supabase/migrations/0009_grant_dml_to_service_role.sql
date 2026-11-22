-- Two faults, both mine, both from 0008.
--
-- ONE: service_role had Dxtm on every table and nothing else -- no SELECT, no
-- INSERT. 0008 asserted that "service_role bypasses RLS by design, it keeps
-- what it has" without checking what it had. Bypassing RLS does not help a
-- role with no table grant: RLS filters rows, the grant decides whether you
-- may look at all. The grouping function reads with the service key, so every
-- call died as an uncaught 500 before reaching any logging.
--
-- This is the same mistake as the authenticated one in 0008, made in the same
-- migration that fixed it, in a comment that claimed the opposite.
--
-- TWO: capture_run was created after 0008's revokes ran, so it picked up the
-- default grants -- including anon=Dxtm, which carries TRUNCATE. 0008's own
-- closing note says a new table needs its grant written next to its RLS. The
-- next table written after that note did not get one.
--
-- service_role is the server-side key: never shipped to a device or a browser,
-- handed to Edge Functions by the platform. The DML it needs is the DML it is
-- for.

grant select, insert, update, delete on all tables in schema public to service_role;

-- capture_run stays as closed as the rest of the slice: the function writes it
-- with the service key, a service-role query reads it, nothing else touches it.
revoke all on table capture_run from anon, authenticated;
