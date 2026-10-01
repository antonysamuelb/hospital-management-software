# Local dev/test harness (NOT what ships to the VM)

This `deploy/dev/` stack exists for one purpose: let Claude (or you) prove the
GNU Health + PostgreSQL pieces actually work together, on a laptop, before
anything touches the real hospital VM.

**This is not the production deployment.** The production path is
`deploy/provision.sh` + `deploy/nginx/` + `deploy/systemd/` running directly
on the VM, per GNU Health's own documented "vanilla" install method — GNU
Health doesn't officially support Docker. This directory is a test harness
only, built to validate that the underlying components (PostgreSQL, Tryton,
the GNU Health modules, the backup approach) behave the way the production
docs say they do.

Findings that came out of building this are reflected back into the
production scripts/docs, e.g. `scripts/backup.sh` was rewritten after this
harness revealed `ghcontrol`'s backup function is just `pg_dump` under a
curses menu, not the scriptable command the original script assumed.
