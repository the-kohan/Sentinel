# Sentinel Network Guard

Docker network guard for local infrastructure — passive surveillance + active alerting for Docker service mesh and host PC network.

## Quick Start

1. Copy `sentinel/sentinel.env.example` to `sentinel/sentinel.env` and fill in your values
2. Build the image: `docker-compose build sentinel`
3. Start the stack: `docker-compose up -d sentinel`
4. Verify: `curl http://127.0.0.1:8100/status`
