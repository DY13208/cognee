# WorkBuddy login

The self-hosted login page uses **Login WorkBuddy**. OAuth authorization codes are
exchanged by the Python backend, with state validation, a ten-minute HttpOnly
state cookie and S256 PKCE. Provider access/refresh tokens are not persisted or
returned to the browser. Cognee issues its own Secure, HttpOnly session cookie.

## Server configuration

Set these variables on the backend (never `NEXT_PUBLIC_*` variables):

```dotenv
CODEBUDDY_ENABLED=true
CODEBUDDY_CLIENT_ID=<client id>
CODEBUDDY_CLIENT_SECRET=<client secret>
CODEBUDDY_REDIRECT_URI=https://127.0.0.1:3030/oauth/callback
CODEBUDDY_SESSION_SECRET=<random secret of at least 32 characters>
CODEBUDDY_SESSION_LIFETIME_SECONDS=604800
CODEBUDDY_AUTHORIZATION_ENDPOINT=https://www.workbuddy.cn/oauth2
CODEBUDDY_TOKEN_ENDPOINT=https://www.workbuddy.cn/oauth2/token
CODEBUDDY_USERINFO_ENDPOINT=https://www.workbuddy.cn/oauth2/userinfo
ENABLE_BACKEND_ACCESS_CONTROL=true
REQUIRE_AUTHENTICATION=true
```

The callback URI must exactly match the provider registration. Production must
use its own client credentials and callback host. The default token endpoint
authentication method is `client_secret_post`; set
`CODEBUDDY_TOKEN_AUTH_METHOD=client_secret_basic` if required by the provider.
`CODEBUDDY_SCOPE` is optional and space-separated. The userinfo response must
contain a stable `sub` or `id`. Only name and email profile fields are stored.

The session lifetime is seconds (604800 = seven days), fixed from login rather
than sliding. Changes apply after backend restart and a new login. Rotating
`CODEBUDDY_SESSION_SECRET` invalidates existing Cognee sessions. Email/password login remains available alongside WorkBuddy; both use the same
session lifetime and secure cookies when WorkBuddy is enabled. Existing password
accounts retain their original data and permissions. API keys still work.

Set `COGNEE_INTERNAL_BACKEND_URL=http://cognee:8000` on the frontend for server
requests, separately from the browser-visible `COGNEE_BACKEND_URL`. The public
UI and API should use the same HTTPS hostname so the host-only cookie reaches
both. A reverse proxy must preserve cookies and support graph WebSockets.
Do not log OAuth callback query strings at the reverse proxy or application.

## Local Docker testing

Put the local backend variables above in the ignored `.env.codebuddy.local`.
Existing `.env` settings are loaded with override enabled by Cognee; avoid
conflicting names in that file. Do not reuse production credentials for testing.

```powershell
docker compose -f docker-compose.yml -f docker-compose.codebuddy-local.yml --profile ui build cognee frontend
docker compose -f docker-compose.yml -f docker-compose.codebuddy-local.yml --profile ui up -d --no-deps --force-recreate cognee frontend codebuddy-https
```

Open `https://127.0.0.1:3030/local-login` (not HTTP or localhost). Caddy issues a
local certificate. Trust its **public root certificate** in your local user
certificate store before browser testing. The TLS private key stays in the
`codebuddy_tls` volume. Local ingress is bound to loopback only.

## Independent identities and team graphs

Each WorkBuddy subject maps to one non-admin Cognee user. Provider email is not
used to automatically link existing accounts. Old account data is retained and
is not automatically exposed to new users. New datasets are private unless
explicitly shared; datasets, graph reads and searches use Cognee's existing ACLs.

Team members can access the **same dataset ID**, not separate copies: its owner
grants `read` to each member, plus `write` if they may update it. Both must first
log in; `GET /api/v1/auth/codebuddy/me` returns the Cognee user ID. As the dataset
owner, call the existing permissions endpoint:

```http
POST /api/v1/permissions/datasets/<member-user-id>?permission_name=read
Content-Type: application/json

["<dataset-id>"]
```

Grant `write` separately when needed, or revoke with DELETE on the same route.
The local UI's workspace ID is a placeholder (`local`), not a real team/tenant;
the existing "Everyone in workspace" control does not provision a local team.
For managed teams, actual tenant membership and tenant ACLs must be configured;
WorkBuddy login alone does not discover or join an organization.

### Share selected existing brains with every WorkBuddy user

Set `CODEBUDDY_SHARED_DATASET_IDS` on the backend to a comma-separated list of
approved dataset UUIDs. Every successful WorkBuddy login grants **read only** on
that exact list, including future users. Other datasets remain private, newly
created datasets are not automatically added, ownership stays unchanged, and
anonymous visitors still cannot access the data. Datasets must be in the same
tenant as the users (the local deployment uses no tenant).

After configuration changes, restart the backend. For already registered users,
run `backfill_shared_read()` from
`cognee.modules.users.authentication.codebuddy_sharing` in the backend process.
Removing an ID from configuration stops future grants; revoke existing ACLs
separately via the permissions DELETE endpoint if access must be removed.
