# PSA ESG Platform

The local stack contains:

- Next.js client: <http://localhost:3000>
- FastAPI server: <http://localhost:8000>
- FastAPI documentation: <http://localhost:8000/docs>
- PostgreSQL: `localhost:5432`

## Prerequisites

Install Docker Engine (or Docker Desktop) with Docker Compose v2.

## Development

Build and start the development stack:

```bash
docker compose -f compose.dev.yml up --build
```

The client and server source directories are mounted into their containers. Next.js and Uvicorn reload when source files change.

Run the stack in the background:

```bash
docker compose -f compose.dev.yml up -d --build
```

View logs:

```bash
docker compose -f compose.dev.yml logs -f
```

Stop the containers:

```bash
docker compose -f compose.dev.yml down
```

Stop the containers and delete development database and build volumes:

```bash
docker compose -f compose.dev.yml down --volumes
```

## Production-like environment

Update the password and other production settings in `.env.local` before starting the stack.

Build and start the production images:

```bash
docker compose --env-file .env.local -f compose.prod.yml up -d --build
```

Check container health and status:

```bash
docker compose --env-file .env.local -f compose.prod.yml ps
```

View production logs:

```bash
docker compose --env-file .env.local -f compose.prod.yml logs -f
```

Stop the production stack without deleting PostgreSQL data:

```bash
docker compose --env-file .env.local -f compose.prod.yml down
```

Production PostgreSQL data is held in the `postgres_prod_data` named volume. Do not add `--volumes` unless you intend to delete that database.

## Rebuild one service

For example, rebuild only the server:

```bash
docker compose -f compose.dev.yml up -d --build server
```

## Configuration

The server receives its database connection through `DATABASE_URL`. Within Docker Compose, services connect to PostgreSQL using the hostname `database`; `localhost:5432` is intended for tools running on the host.

`NEXT_PUBLIC_API_URL` is compiled into the production Next.js bundle. Set it to the browser-accessible API URL before building the client image.
