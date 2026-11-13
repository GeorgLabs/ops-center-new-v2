# Before this goes on GitHub

Do these in order. 15 minutes.

## 1. Secrets and private data (the ones that matter)

- [ ] `.env` and `opscenter.db` are **not** tracked. The `.gitignore` covers both. Check after `git add .`:
      `git status` must not list them, and `git ls-files | grep -E "\.env$|\.db$"` must print nothing.
- [ ] Start with a **fresh** repo (`git init` in a clean copy of the folder). Do not reuse a folder that already has history.
- [ ] If a secret was ever committed (even deleted afterwards), it is in the history. Fix: generate a new
      `OPS_SECRET_KEY` and delete the repo/history before pushing. Changing the file later is not enough.
- [ ] Look through the code once for anything personal or secret: `git grep -nIiE "password|secret|token|key" -- . ':!static/vendor'`
      (expect only code that handles them, never real values).
- [ ] Commit identity: GitHub shows the e-mail in every commit. Use the private address:
      GitHub -> Settings -> Emails -> "Keep my email addresses private", then
      `git config user.email "<id>+<username>@users.noreply.github.com"` and `git config user.name "<name or nickname>"`.
- [ ] GitHub account: two-factor authentication on.

## 2. Make the repo yours

- [ ] Fill in the three `<...>` placeholders at the bottom of `README.md` (your name, mentor, license).
- [ ] **License:** add a `LICENSE` file (MIT is the usual choice for a small project). Keep `static/vendor/swagger-ui/LICENSE` and `NOTICE`.
- [ ] Mission Control and Traffic are already switched off in `app/main.py` (the lines are commented out). `app/dev/` can stay or be deleted.
- [ ] Agree on credit and publishing: decide the wording in "Credits", and check that the employer is fine with it being public.
- [ ] `.gitattributes` is included on purpose: it keeps `.bat` files on Windows line endings and `.sh`/Dockerfile on Linux ones.

## 3. Quality (this is what visitors judge)

- [ ] `python -m ruff check .` is clean and `python -m pytest` passes.
- [ ] `.env.example` contains only placeholders (it does - keep it that way).
- [ ] The admin password in your local `.env` is **not** the one you use anywhere else. Change it in the app (Account) once.

## 4. Docker works

- [ ] `docker compose up -d --build`, open <http://127.0.0.1:8000>, log in with the admin from `.env`, create a user, change a password, create a host, run the agent (`agent/README.md`) against it.
- [ ] `docker compose logs` shows no errors. `docker compose down`, `up -d` again: the users and hosts are still there, and the admin password you changed in the app still works (the `.env` one does not - that is correct).
- [ ] Mission Control, Traffic and `/docs` are **not** reachable in the container (404 is correct).
- [ ] A **second** start with a different `OPS_ADMIN_PASSWORD` in `.env` does not change the admin password (it must not).

## 5. First push

```bash
git init -b main
git add .
git status                      # last look: no .env, no .db
git commit -m "Ops Center: FastAPI + SQLModel server monitor"
# create an empty repo on github.com first (no README/licence there), then:
git remote add origin https://github.com/<user>/<repo>.git
git push -u origin main
```

Tip: create it as **private** first, look at it in the browser as a stranger would, then make it public.
