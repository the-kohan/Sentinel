# Sentinel Network Guard

God-mode network guard for local infrastructure — passive surveillance + active alerting for Docker service mesh and host PC network.

## Quick Start

1. Copy `sentinel/sentinel.env.example` to `sentinel/sentinel.env` and fill in your values
2. Build the image: `docker-compose build sentinel`
3. Start the stack: `docker-compose up -d sentinel`
4. Verify: `curl http://127.0.0.1:8100/status`

## Documentation

| File | Purpose |
|---|---|
| `README.md` | Project overview |
| `01_Architecture.md` | As-built layers, data flow, actual code paths |
| `02_Deployment.md` | Dockerfile, requirements, compose entry, env vars |
| `03_Database.md` | Live schema, table counts, allowlist contents |
| `04_Source_Files.md` | Inventory of every code file with key snippets |
| `05_Collectors.md` | Host + Docker collector scripts and output format |
| `06_API.md` | FastAPI endpoints and current responses |
| `07_Alerting.md` | Notifier, webhook target, Telegram fallback |
| `08_State.md` | Current runtime state, divergences, known bugs |

## Security

- `sentinel/sentinel.env` is gitignored and must NOT be committed
- `sentinel/sentinel.env.example` contains only placeholders
- `collector-data/` contains local runtime observations and is gitignored
- `seed_allowlist.sql` and `03_Database.md` contain example allowlist entries only; do not commit your actual `known_good` data
