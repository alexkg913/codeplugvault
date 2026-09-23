# Codeplug Vault

A private, fleet-scoped inventory app for tracking radios (and, later, batteries and
codeplug configurations) for small teams — built around the needs of racing spotters
managing a handful of radios from a phone at the track.

See `Codeplug_Vault_Project_Brief.md` for the full product brief and milestone plan.
This README covers what's actually implemented so far: **Milestone 0** (foundation),
**Milestone 1** (radio inventory), and **Milestone 2** (batteries and maintenance).

## Stack

- Python 3.12, Django 5.2 (LTS)
- PostgreSQL (including for local development, via Docker Compose)
- Server-rendered Django templates, no frontend framework, no web fonts — the whole UI
  is a single hand-written stylesheet (`static/css/main.css`) on the system font stack,
  so there's nothing to download before the page can paint
- pytest / pytest-django, ruff, black

## Local setup

1. Start Postgres:
   ```
   docker compose up -d db
   ```
2. Create a virtualenv and install dependencies:
   ```
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements-dev.txt
   ```
3. Copy the environment file and adjust if needed (defaults match `compose.yaml`):
   ```
   cp .env.example .env
   ```
4. Run migrations:
   ```
   python manage.py migrate
   ```
5. Create an account. There's no public signup yet (see "Model & role rules" below), so
   create your own login with:
   ```
   python manage.py createsuperuser
   ```
6. Run the dev server:
   ```
   python manage.py runserver
   ```
7. Sign in at `/accounts/login/`. On first sign-in with no fleet yet, you'll be routed to
   a "create your fleet" page. From there you can add radios.

## Checks and tests

```
ruff check .
black --check .
python manage.py check
python manage.py makemigrations --check --dry-run
pytest
```

CI (`.github/workflows/ci.yml`) runs all of the above against a Postgres service
container on every push/PR.

## Model & role rules

This is the short design-decisions record the project brief asks for, kept close to the
code so it stays accurate. Update it as the model evolves.

**Tenancy.** Every domain record (`Radio`, and everything added in later milestones)
belongs to exactly one `Fleet`. There is no cross-fleet visibility, ever. Access is
never inferred from a submitted `fleet_id` — every fleet-scoped view resolves the fleet
from the URL and re-checks the caller's `Membership` server-side on every request
(`apps/radios/permissions.py:FleetScopedMixin`). A user who isn't an active member of a
fleet gets a 404 on that fleet's pages, not a 403 — this avoids confirming a fleet's
existence to people outside it.

**Roles.** `Membership.role` is one of `owner`, `editor`, `viewer`. Owners and editors
can mutate fleet records; viewers can only read. Role checks happen on every mutating
view (POST), not just in template button visibility. A fleet can never be left with zero
active owners — see `apps/fleets/services.py` (`LastOwnerError`, enforced by
`change_membership_role` / `deactivate_membership`).

**Onboarding.** There's no public signup form in this milestone — accounts are created
via `manage.py createsuperuser` or the Django admin (the brief's "owner-created
accounts" default). A signed-in user with no active membership anywhere is routed to a
one-field "create your fleet" form, which creates a `Fleet` and an `owner` `Membership`
for them in one step. Adding *other* members to a fleet is currently admin-only; a
proper invite flow is out of scope for M0/M1.

**Identifiers.** `Fleet` and `Radio` both expose a random `public_id` (UUID4) used in
URLs instead of their database primary key, so URLs don't leak sequential IDs. This is
enumeration resistance, not access control — every lookup by `public_id` still goes
through the membership check above.

**Archiving, not deleting.** Radios are archived (`archived_at` set), never hard
deleted, so programming/maintenance history added in later milestones stays intact. The
default inventory list excludes archived radios; a filter toggle shows them, and an
archived radio's detail page and edit history remain reachable directly.

**Duplicate asset labels.** `asset_label` must be unique within a fleet (enforced by a
`UniqueConstraint` and re-checked in `RadioForm.clean_asset_label` / `BatteryForm.clean_asset_label`,
since the DB constraint alone doesn't catch it when the form excludes `fleet` as a
field). The same label is fine in a different fleet.

**Battery assignment is a swap, not a pointer.** There's no mutable "current battery"
field on `Radio`. Instead, `BatteryAssignment` rows form a full history, and at most one
row per battery (and per radio) may be active (`ended_at IS NULL`) at a time — enforced
by partial `UniqueConstraint`s at the database level, not just in application code.
`apps/radios/services.assign_battery` is the only path that creates a new assignment: it
ends whichever assignment is currently active for the battery *and* whichever is active
for the radio in the same transaction, so assigning a battery that's already elsewhere
reads as a swap rather than an error. Cross-fleet pairings raise `CrossFleetError`, and
the form's battery choices are scoped to the current fleet, so a forged battery id from
another fleet never validates in the first place.

**Maintenance events are append-only** in this milestone: a radio's timeline can be
added to but not edited or deleted through the UI (only via the Django admin). Full
correction semantics (an audited edit history) are a Milestone 3+ concern per the brief.

## What's next

Milestone 3 (configuration families, versions, channel snapshots, file attachments, and
programming records) is the next planned milestone and is **not** implemented yet.
