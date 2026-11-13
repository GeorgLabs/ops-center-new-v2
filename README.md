# Ops Center

A small self-hosted server monitor. Machines report their CPU, memory and disk usage with a tiny agent;
the web dashboard shows them live. Users, an admin panel and password changes are built in.

**Stack:** FastAPI · Pydantic · SQLModel · SQLite (Alembic migrations) · Argon2 password hashing · JWT login

## Features

- Dashboard with live charts per host, plus a "this machine" page (CPU, memory, disk, top processes)
- Hosts report with their own API key (shown once, stored only as a hash)
- **Accounts:** register (can be switched off), log in, change your own password
- **Admin panel:** overview numbers, create users, make/remove admin, disable/enable accounts,
  set a new password for someone who forgot theirs, delete users (with their hosts), see and delete any host
- **First administrator from `.env`:** created at startup, only if that user does not exist yet
- **Standalone agent** (`agent/`): runs on its own, needs nothing from the server code
- Security built in: rate-limited login and password check, no user enumeration, a password change or disabled account
  ends running sessions at once, hardened token checks, strict security headers and CSP, no secrets in responses,
  owner checks on every host route

## Quick start

### Without Docker

Windows: double-click `setup.bat`, then `run.bat`. Linux/macOS: `./setup.sh`, then `./run.sh`.
(Python 3.11-3.13; 3.13 is the best choice.) `setup` creates `.env` with random secrets and **prints the admin
password once** (it is also written to `.env`). Open <http://127.0.0.1:8000> and log in as `admin`.

Another port: edit `PORT` in `run.bat`, or `PORT=8001 ./run.sh`.

### With Docker

```bash
python scripts/init_env.py      # creates .env (or copy .env.example to .env and fill it in by hand)
docker compose up -d --build
```

Open <http://127.0.0.1:8000>. The database lives in the `opscenter-data` volume and survives restarts and rebuilds.
Compose refuses to start without `OPS_SECRET_KEY`, `OPS_ADMIN_USERNAME` and `OPS_ADMIN_PASSWORD`, so a fresh install
always has an administrator. The port is bound to `127.0.0.1` on purpose: to reach it from other machines put a reverse
proxy with HTTPS in front (Caddy, nginx) - do not publish port 8000 on the internet as it is.

```bash
docker compose logs -f        # logs
docker compose down           # stop (keeps data)   |   docker compose down -v   # stop AND delete data
```

## The administrator from `.env`

```
OPS_ADMIN_USERNAME=admin
OPS_ADMIN_PASSWORD=at-least-12-characters
```

At every start the server checks: *is there a user with this name?* If **not**, it creates it as an administrator.
If **yes**, it does nothing - it never changes an existing account. That means:

- The password in `.env` is only the **starting** password. Change it later in the app (**Account → Change password**);
  editing `.env` afterwards has no effect.
- Forgot the admin password? Another admin can set a new one (**Admin → New password**). If you were the only admin,
  delete the database (or the user row) and restart: the admin is created again from `.env`.
- Leave both variables out and no admin is created (then nobody can open the admin panel).
- Set both or neither; the password needs 12-128 characters. A wrong setting stops the server at startup with a clear message.

Rules inside the admin panel: you cannot disable, demote, delete or reset **yourself** there, so one working
administrator always remains. Disabling a user or setting a new password signs them out immediately.

## Connect a machine (agent)

In the dashboard: **Hosts → New host** and copy the API key (shown once). On the machine you want to watch:

```bash
cd agent
pip install -r requirements.txt
python agent.py --url http://127.0.0.1:8000 --key-file key.txt     # key.txt contains just the key
```

The `agent/` folder is independent: copy only that folder to the other machine. Details, a systemd service and Windows
autostart are in [`agent/README.md`](agent/README.md).

## Configuration

Environment variables (or the `.env` file), prefix `OPS_`:

| variable | default | meaning |
|---|---|---|
| `OPS_SECRET_KEY` | **required**, 32+ chars | signs login tokens |
| `OPS_ADMIN_USERNAME` / `OPS_ADMIN_PASSWORD` | not set | first administrator (see above), both or neither |
| `OPS_ALLOW_REGISTRATION` | `true` | `false` = only admins create accounts |
| `OPS_DATABASE_URL` | `sqlite:///opscenter.db` | database (Docker uses `/data/opscenter.db`) |
| `OPS_DEV` | `0` | `1` = also serve `/docs` (API explorer). Never on a real server |
| `OPS_ACCESS_TOKEN_MINUTES` | `30` | how long a login stays valid |
| `OPS_ONLINE_WINDOW_SECONDS` | `60` | a host is "online" if it reported this recently |

## API in one table

| | |
|---|---|
| `POST /api/auth/register`, `POST /api/auth/token` | create account / log in (form data) |
| `GET /api/auth/me`, `POST /api/auth/password` | who am I / change my password (returns a fresh token) |
| `GET /api/config` | public: is registration open? |
| `GET/POST/DELETE /api/hosts`, `GET /api/hosts/{id}/metrics` | my hosts |
| `POST /api/ingest` | agents report here (`X-API-Key` header) |
| `GET /api/system`, `/api/system/processes` | this machine |
| `/api/admin/stats`, `/api/admin/users…`, `/api/admin/hosts…` | admin only (403 for everybody else) |

Start with `OPS_DEV=1` and open `/docs` to try them.

## Tests

```bash
python -m pytest
python -m ruff check .
```

## Layout

```
app/            backend: routers/, models.py, schemas.py, security.py, bootstrap.py, config.py ...
migrations/     Alembic database migrations (run automatically at startup)
static/         web interface (plain HTML/CSS/JS, no build step)
agent/          the standalone reporting agent
tests/          pytest
```

`app/dev/` holds two optional learning tools (a live request log "Traffic" and "Mission Control", a set of
self-checks). They are switched off: to enable them, remove the leading `# ` from the marked lines in `app/main.py`
and start with `OPS_DEV=1`.

## Known limits

- The rate limiters and their counters live in memory: run **one** worker process (the Dockerfile does).
- Tokens are kept in the browser's `sessionStorage` (gone when the tab closes). That is simple and avoids CSRF;
  the price is that a script injection bug would expose them - which is why the page never uses `innerHTML` and the CSP is strict.
- SQLite is fine for a handful of hosts; for more, switch `OPS_DATABASE_URL` to PostgreSQL. Old measurements are not
  deleted automatically yet (a retention job would be a good next feature).
- Behind a reverse proxy all clients share the proxy's address: the login limit then counts per username.
- Back up the database (`/data/opscenter.db` in Docker) - it is the only state.

## Credits and license

Backend: <YOUR NAME>. Dashboard (`static/`) and the project skeleton were provided as part of a learning
project by <MENTOR>. Swagger UI (`static/vendor/`) is Apache-2.0, see the licence files in that folder.

License: <choose one, e.g. MIT - add a LICENSE file>
