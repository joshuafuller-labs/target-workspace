# Postgres Runtime Defaults

Target Workspace still supports SQLite for local development and small
single-node dogfood runs, but production deployments should use Postgres.

## Database URL

Set `TW_DATABASE_URL` to a SQLAlchemy Postgres URL, for example:

```text
postgresql+psycopg://tw:${POSTGRES_PASSWORD}@db:5432/target_workspace
```

The production compose file already uses this form.

## Pool Sizing

Set `TW_DATABASE_WORKER_COUNT` to the number of application worker processes.
The SQLAlchemy pool is sized as:

```text
pool_size = workers * 2 + 4
max_overflow = 0
```

`max_overflow=0` keeps total database concurrency predictable. If pgbouncer is
in front of Postgres, size pgbouncer and Postgres connection limits for the sum
of all app replicas using this formula.

## Connection Defaults

Postgres engines are created with:

```text
pool_pre_ping = true
pool_recycle = 1800
statement_timeout = 30000 ms
idle_in_transaction_session_timeout = 60000 ms
```

These defaults fail slow queries and abandoned transactions before they can pin
connections indefinitely.

SQLite URLs keep their existing `check_same_thread=false` behavior and do not
receive Postgres pool tuning.
