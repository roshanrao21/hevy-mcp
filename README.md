# Hevy MCP

A guarded Model Context Protocol server for the official Hevy fitness API.

## What it exposes

Read tools:

- `list_workouts`
- `get_workout`
- `list_routines`
- `get_routine`
- `search_exercise_templates`
- `get_exercise_history`

Write tools:

- `create_routine`
- `update_routine`
- `create_workout`

Write tools are disabled by default and require the exact tool argument
`confirmation="CONFIRM"` after the final payload has been reviewed.

## Important Hevy constraints

- Hevy API access currently requires Hevy Pro and an API key.
- The API is marked early-stage, so endpoint/schema changes are possible.
- The official API currently has no general delete operations for the supported entities.
- A Hevy API key must never be placed in a prompt, tool argument, URL, log, screenshot,
  source repository, or Docker image.

## Architecture

```text
MCP client
   |
   | stdio, or HTTPS Streamable HTTP
   v
Hevy MCP
   |
   | api-key header
   v
Official Hevy API
```

The server is stateless. In shared HTTP mode, each caller supplies their own Hevy key in
the `X-Hevy-API-Key` transport header. The key is held only for the request and forwarded
to Hevy as `api-key`.

For a serious public service, replace raw per-request Hevy keys with an OAuth login plus
an encrypted credential vault. Do not operate a giant shared secret spreadsheet. Humanity
has tested that architecture thoroughly.

## Local setup

Requirements:

- Python 3.11+
- Hevy Pro
- Hevy API key from Hevy's developer settings

```bash
cp .env.example .env
# Set HEVY_API_KEY in .env
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
hevy-mcp
```

The default transport is `stdio`.

Example local client configuration:

```json
{
  "mcpServers": {
    "hevy": {
      "command": "/absolute/path/hevy-mcp/.venv/bin/hevy-mcp",
      "env": {
        "HEVY_API_KEY": "YOUR_KEY",
        "MCP_TRANSPORT": "stdio",
        "ALLOW_WRITES": "false"
      }
    }
  }
}
```

Keep the key in your client's secret/environment facility where available.

## Test with MCP Inspector

For HTTP mode:

```bash
MCP_TRANSPORT=streamable-http \
HEVY_API_KEY="$HEVY_API_KEY" \
MCP_ACCESS_TOKEN="$(openssl rand -hex 32)" \
hevy-mcp
```

Connect Inspector to:

```text
http://localhost:8000/mcp
```

Send the configured bearer token in `Authorization`.

## Docker deployment

```bash
cp .env.example .env
```

Set at minimum:

```dotenv
MCP_TRANSPORT=streamable-http
HOST=0.0.0.0
PORT=8000
MCP_ACCESS_TOKEN=<long-random-token>
ALLOW_HEADER_HEVY_KEY=true
ALLOW_WRITES=false
```

Then:

```bash
docker compose up -d --build
curl http://localhost:8000/health
```

The container:

- runs as a non-root user
- uses a read-only filesystem
- drops Linux capabilities
- enables `no-new-privileges`
- includes a health check

## Make it safely usable by other people

### Small trusted group

Deploy behind an HTTPS reverse proxy and require:

- a unique gateway token per environment, preferably per user
- `X-Hevy-API-Key` supplied by each user's MCP client
- strict origin allowlisting if browser clients are supported
- rate limiting at the proxy and application
- access logs with secrets redacted
- `ALLOW_WRITES=false` until mutation workflows are reviewed

Example headers:

```text
Authorization: Bearer <your-mcp-gateway-token>
X-Hevy-API-Key: <the-user's-hevy-key>
```

### Public production service

Do not ask users to hand a permanent Hevy API key to your website without a proper
credential system. Build:

1. User login with OAuth/OIDC for your service.
2. Encrypted per-user secret storage using KMS or a managed secret vault.
3. Short-lived MCP access tokens bound to user and tenant.
4. Server-side retrieval of the correct Hevy key after authentication.
5. Per-tool authorization scopes such as `hevy:read` and `hevy:write`.
6. Explicit approval UI for mutations.
7. Audit records containing user, tool, target ID, timestamp, and result, but no secret.
8. Revocation, account deletion, key rotation, abuse detection, and privacy controls.

MCP recommends OAuth for remote authorization. A raw bearer gateway token is included here
as a deployable baseline, not as the final identity system for a consumer SaaS.

## Reverse proxy example with Caddy

```caddyfile
mcp.example.com {
    reverse_proxy hevy-mcp:8000
    encode zstd gzip

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "no-referrer"
    }
}
```

Caddy provisions TLS automatically when DNS points to the server and ports 80/443 are open.

## Cloud deployment outline

The Docker image can run on:

- Google Cloud Run
- AWS ECS/Fargate
- Azure Container Apps
- Fly.io
- Render
- a VM with Docker and Caddy
- Kubernetes

Minimum production configuration:

- HTTPS only
- secrets from the cloud secret manager, never image/environment files committed to Git
- at least two instances only after moving rate limiting to Redis or the gateway
- bounded request/body sizes
- outbound egress restricted to `api.hevyapp.com`
- alerting on authentication failures, 429s, and upstream errors
- dependency and container scanning
- pinned image digests and a rollback path

## Guardrails implemented

- Read/write separation
- writes disabled by default
- exact confirmation token for every mutation
- typed bounds for weight, reps, time, distance, notes, and object counts
- no delete or arbitrary HTTP tools
- no arbitrary shell, SQL, file, or URL access
- no secret accepted as an MCP tool argument
- per-request credential context
- rate limiting
- bounded page sizes
- timeouts and safe retries only for GET operations
- structured, non-secret errors
- non-root/read-only container
- medical-safety instruction and resource
- idempotency annotation on replacement updates
- warnings that creates may duplicate on retry

## Known limitations

- The in-memory limiter is per process. Use a gateway or Redis for multiple replicas.
- The shared-header mode depends on the MCP client supporting custom headers.
- Exact Hevy request schemas may evolve because the upstream API is early-stage.
- `update_routine` is a replacement operation. Always fetch and review the current routine.
- The project intentionally implements a focused tool set instead of exposing every endpoint.
  Broad generic API proxy tools are easier to build and much easier to regret.
