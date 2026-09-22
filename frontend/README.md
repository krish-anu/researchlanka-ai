# Frontend

Next.js App Router frontend for the ResearchLanka research analytics platform.

- `src/app/` — routes
- `src/components/` — reusable UI components
- `src/services/` — API clients, auth, and local state
- `src/types/` — shared TypeScript types

## Roles

The web app recognises three roles. `guest` is not stored anywhere — it is what
the app assumes when no valid session cookie is present, so "unsigned visitor"
is a role rather than the absence of one, and every gate is a single
`can(role, capability)` call. The grant table is `src/services/auth/permissions.ts`.

| Role | Who | Can |
|---|---|---|
| `guest` | anyone on the open web | search and read the corpus, browse profiles, download exports |
| `user` | signed-in researcher or analyst | everything above, plus a saved library and flagging suspect records |
| `admin` | platform steward | everything above, plus `/admin`: pipeline console, entity-resolution queue, flag triage, account and role management |

Routes are gated in three places, with different jobs:

1. `src/middleware.ts` — fast redirect so a protected page never starts rendering.
2. The route's own layout (`app/admin/layout.tsx`, `app/account/layout.tsx`) — the
   check that actually enforces the rule, in the same request as the render.
3. Each server action — re-checked independently, because an action is a public
   endpoint and a hidden button is no guarantee it is never invoked.

Self-registration only ever creates `user`. Administrators are promoted from
`/admin/users` by an existing administrator, and the last active administrator
can neither be demoted nor suspended.

## Accounts and local state

The ResearchLanka API is read-only and has no accounts, write endpoints or
notion of a role — `backend/src/api/routing/routes.py` dispatches GET only. So
accounts, saved libraries, record flags and resolution decisions are owned by
this app and stored as JSON under `.data/` (`src/services/store/jsonFile.ts`).

That store is the smallest thing that works, not a database: writes are
serialised per file and atomic within one Node process, but it does not survive
a multi-instance deployment. **Replace it before running more than one server.**

Sessions are stateless HMAC-signed cookies (`src/services/auth/session.ts`), so
there is no session table to run. Server-side route guards re-check the user
store, so suspensions and role changes apply on the next guarded request.

## Running

```bash
npm install
npm run dev
```

### Test accounts

With no `ADMIN_PASSWORD` configured, two fixed accounts are seeded on first
read, one per signed-in role, so both sides of the role system can be exercised
without going through sign-up:

| Email | Password | Role |
|---|---|---|
| `admin@example.com` | `password123` | `admin` |
| `user@example.com` | `password123` | `user` |

They are recreated if missing, so deleting one from `.data/users.json` brings it
back on the next request. **These credentials are public.** Set
`SEED_TEST_ACCOUNTS=false`, or configure `ADMIN_EMAIL` and `ADMIN_PASSWORD`,
anywhere that is not a test machine — with `ADMIN_PASSWORD` set, only that one
administrator is seeded and the test pair is never created.

See `.env.example` for every variable, including the `AUTH_SECRET` that signs
session cookies (required in production).

The pages fetch the Python API server-side; a cold or unreachable API is a
normal state when running only the frontend, and every page renders an
explanatory panel rather than crashing.

## AI research interface

The public interface uses the forest-green design approved in
`../design-preview/researchlanka-ui-preview.html`. All displayed figures come
from the API; the HTML prototype's sample records are not used in the app.
The backend's accepted-AI review boundary remains authoritative.

- Overview: year/field filters, annual area/line/bar views with an open-access
  comparison, field donut/mosaic/bar views, institution rankings, field/year
  heatmap, collaboration metrics, and recent publications.
- Publications: switch between the compact table and full metadata cards;
  existing search, facets, sorting, pagination, CSV/JSONL exports, and record
  actions remain available.
- Institutions: rankings, output/open-access scatter plot, profiles, and the
  existing two/three-institution comparison.
- Researchers: profile cards or the original ranking table, preserving name
  disambiguation notes, profile history, publications, and co-author networks.
- Topics: the domain/field/subfield hierarchy, proportional charts, per-page
  exports, field activity, and the existing topic directory. NMF topics require
  the backend's model artifacts; an unavailable model is shown as a data error.
- Collaboration: institution/researcher/country scopes, year/field filters,
  minimum edge weight, node limit, size metrics, node exploration, profile
  navigation, graph reset, PNG/CSV downloads, centrality and community tables.
- Data quality: source completeness, source coverage, original quality metrics,
  conflicts, limitations, and required disclosures.

Chart tables remain available for keyboard and screen-reader access. The
layout responds to mobile screens and the existing system dark-mode preference.
Authentication, saved records, flagging, role gates, and all administration
routes continue to use their existing services and server actions. Browser
exports use the same-origin `/api/v1` rewrite.

Validation: `npm run lint`, `npm test`, `npm run check:palette`, `npm run build`.

Local integration checks found three existing configuration prerequisites:
NMF topic artifacts for the topic directory, matching
`RESEARCHLANKA_ADMIN_API_TOKEN` values for backend administrative actions, and
`AUTH_SECRET` for production sign-in. The redesign preserves their existing
unavailable/error states; it does not create model artifacts or alter secrets.
Development sign-in and all public, account, and admin navigation were checked.
