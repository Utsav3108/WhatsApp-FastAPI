# PostgreSQL Developer Cheat Sheet (Ripple)

## Connect to PostgreSQL

Connect directly to the PostgreSQL database running inside Docker:

```bash
docker exec -it whatsapp_postgres psql -U postgres -d ripple
```

Exit PostgreSQL:

```sql
\q
```

---

# Database Inspection

## List all databases

```sql
\l
```

## Connect to a database

```sql
\c ripple
```

## Show all tables

```sql
\dt
```

## Describe a table

```sql
\d challenges
```

## Show detailed table information

```sql
\d+ challenges
```

## Count rows

```sql
SELECT COUNT(*) FROM challenges;
```

---

# Enum Management

## List all enums

```sql
SELECT typname
FROM pg_type
WHERE typtype = 'e';
```

## Drop an enum

```sql
DROP TYPE challenge_difficulty;
```

## Force drop an enum

```sql
DROP TYPE challenge_difficulty CASCADE;
```

---

# Table Management

## Remove all data from a table

```sql
TRUNCATE TABLE challenges;
```

## Remove all data and reset auto-increment IDs

```sql
TRUNCATE TABLE challenges RESTART IDENTITY;
```

## Drop a table

```sql
DROP TABLE challenges;
```

## Drop a table and all dependent objects

```sql
DROP TABLE challenges CASCADE;
```

---

# Schema Management

## View current schema

```sql
SELECT current_schema();
```

## Drop entire schema and everything inside it

⚠️ Deletes ALL tables, enums, indexes, constraints, and views.

```sql
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
```

This is the preferred command during development when you want a completely clean database.

---

# Database Management

## Create a database

```sql
CREATE DATABASE ripple;
```

## Switch to postgres database

```sql
\c postgres
```

## Drop a database

```sql
DROP DATABASE ripple;
```

## Recreate database

```sql
DROP DATABASE ripple;
CREATE DATABASE ripple;
```

---

# Docker Commands

## Start PostgreSQL only

```bash
docker compose up -d postgres
```

## Start PostgreSQL and Redis only

```bash
docker compose up -d postgres redis
```

## View running containers

```bash
docker ps
```

## View PostgreSQL logs

```bash
docker logs whatsapp_postgres
```

## Stop PostgreSQL

```bash
docker stop whatsapp_postgres
```

## Restart PostgreSQL

```bash
docker restart whatsapp_postgres
```

---

# Complete Development Reset

## Option 1: Reset database contents

Connect to PostgreSQL:

```bash
docker exec -it whatsapp_postgres psql -U postgres -d ripple
```

Run:

```sql
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
```

Restart FastAPI:

```bash
uvicorn app.main:app --reload
```

SQLAlchemy create_all() will recreate all tables.

---

## Option 2: Destroy PostgreSQL volume completely

⚠️ Deletes all PostgreSQL and Redis data.

```bash
docker compose down -v
```

Recreate containers:

```bash
docker compose up -d postgres redis
```

---

# Backup & Restore

## Backup entire database

```bash
docker exec whatsapp_postgres pg_dump -U postgres ripple > ripple.sql
```

## Restore database

```bash
cat ripple.sql | docker exec -i whatsapp_postgres psql -U postgres ripple
```

## Backup a single table

```bash
docker exec whatsapp_postgres pg_dump -U postgres -t challenges ripple > challenges.sql
```

---

# Useful Queries

## List all tables

```sql
SELECT tablename
FROM pg_tables
WHERE schemaname = 'public';
```

## List all enum types

```sql
SELECT typname
FROM pg_type
WHERE typtype = 'e';
```

## List all columns of a table

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'challenges';
```

## Show PostgreSQL version

```sql
SELECT version();
```

---

# Ripple PostgreSQL Connection

Local development:

```env
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/ripple
```

FastAPI Engine:

```python
engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)
```
