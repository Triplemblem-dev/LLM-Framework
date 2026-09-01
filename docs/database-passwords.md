# Database passwords and recovery

The root `.env` file contains two unrelated secrets:

| Setting | Purpose | Does editing `.env` change it immediately? |
| --- | --- | --- |
| `APP_ACCESS_TOKEN` | Signs in to the framework | Yes, after recreating the backend |
| `POSTGRES_PASSWORD` | Authenticates the backend to PostgreSQL | Only before the database volume is initialized |

PostgreSQL reads `POSTGRES_PASSWORD` when Docker creates `postgres_data` for
the first time. After that, the real password belongs to the database role
inside PostgreSQL. Editing `.env` changes what the backend attempts to use; it
does not rewrite the initialized role. Recreating only the backend therefore
cannot repair a mismatch.

## Choose portable secrets

Use a password manager or generate a 64-character hexadecimal value on macOS
or Linux:

```bash
openssl rand -hex 32
```

The backend receives the PostgreSQL fields separately and constructs a
structured SQLAlchemy URL, so database passwords are not inserted raw into URL
syntax. Hexadecimal values are still recommended because they also avoid shell,
Compose `.env`, clipboard, and cross-platform quoting mistakes.

## Change the application access token

Edit only `APP_ACCESS_TOKEN` in the root `.env`, then run:

```bash
docker compose up -d --build backend frontend
```

Reload the browser and sign in with the new value. This does not change the
database password.

## Rotate the database password and preserve data

Keep the terminal inside the cloned repository. Open a local PostgreSQL prompt
inside the running database container:

```bash
docker compose exec postgres sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

At the `psql` prompt, run:

```text
\password
```

Enter the new database password twice. PostgreSQL does not display it. Exit:

```text
\q
```

Set that exact value as `POSTGRES_PASSWORD` in the root `.env`, then recreate
the backend:

```bash
docker compose up -d --no-deps --force-recreate backend
```

Verify recovery:

```bash
docker compose ps
docker compose logs --tail=100 backend
curl -fsS http://127.0.0.1:8000/health
```

The backend should remain running, its logs should include `Database
bootstrapped and seeded.`, and the health endpoint should return
`{"status":"ok"}`.

## Start over without preserving anything

Only use this path when the database, documents, downloaded Docker Ollama
models, and gateway state may all be permanently deleted:

```bash
docker compose down -v
docker compose up -d --build
```

The `-v` flag deletes the named Docker volumes. This cannot be undone without
an external backup.

## Troubleshooting

If the backend log contains `password authentication failed`, it prints an
actionable explanation. The usual causes are:

- `POSTGRES_PASSWORD` was edited after `postgres_data` was initialized;
- Compose was run from a different checkout with a different `.env`;
- multiple checkouts used the same Compose project name; or
- a shell-level `POSTGRES_PASSWORD` overrode the `.env` value.

Check for a shell override without printing the password:

```bash
if printenv POSTGRES_PASSWORD >/dev/null; then
  echo "Shell override found"
else
  echo "No shell override"
fi
```

If an override is unintended, run `unset POSTGRES_PASSWORD` in that terminal
before recreating the backend. Do not paste passwords, `.env` contents, or a
full unredacted `docker compose config` into issue reports.

For deliberate native development, an explicit `DATABASE_URL` remains
supported and takes precedence over the separate PostgreSQL fields.
