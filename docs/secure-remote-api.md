# Secure remote API — implementation record

## Current support boundary

The repository contains an optional secure remote API, but it is not yet a
promoted public release feature. The API contract, authentication boundary,
runtime dispatch, frontend production build, Compose configuration, and a live
loopback Caddy route have been tested. Real-device LAN and Tailscale acceptance
tests on Windows, macOS, and Linux still remain before this feature should be
advertised in the main README.

Fresh and existing installations remain in **Off** mode unless the owner
deliberately configures and enables remote access.

## What is implemented

```text
Phone or laptop
      ↓ HTTPS + device bearer key
Tailscale Serve (private tailnet only)
      ↓ host loopback
Caddy gateway (optional Compose profile)
      ↓ fixed internal route + gateway secret
Framework /v1 API
      ↓ domain prompt, documents, memory, and saved tuning
Local model runtime
```

- `GET /v1/models` lists only the domains permitted for that device key.
- `POST /v1/chat/completions` supports OpenAI-compatible JSON and SSE
  responses, including the `[DONE]` marker.
- The supported request subset is `model`, `messages`, `stream`, `n=1`,
  `user`, `temperature`, `top_p`, and `max_tokens`. Unknown fields are
  rejected. The three sampling/output fields are accepted for client
  compatibility but ignored because the domain's saved settings are
  authoritative.
- API calls are stateless and do not add conversations to the framework UI.
- The selected virtual model is `domain/<domain-uuid>`; the domain chooses the
  actual local model, context length, answer limit, and sampling settings.
- Client `system` and `developer` messages are treated as untrusted client
  instructions and cannot replace the framework's protected prompt layers.
- Every device receives a separately named, domain-scoped, revocable key.
  Only a SHA-256 hash is stored; plaintext is returned once at creation.
- Expiration and per-key request limits are supported by the backend. Failed
  authentication attempts and concurrent remote generations are bounded.
- The existing application access token is not accepted as a remote device
  key.
- Tailscale Serve is the recommended private-VPN transport. It terminates
  trusted HTTPS while Docker publishes the gateway on host loopback only.
- Caddy exposes only `/health` and `/v1/*`, preserves streaming, adds a secret
  gateway-to-backend header, and has request access logging disabled.
- Ports 3000 and 8000 bind to loopback by default. PostgreSQL and Ollama are
  not published by Compose.
- Remote access can be disabled in the UI immediately without stopping local
  framework use.

## Local model runtimes

Ollama remains the default and continues to use its native local API. An
optional generic local OpenAI-compatible adapter can list and stream models
served by llama.cpp, LocalAI, or vLLM. Generic model references use the prefix
`openai-local/` inside the framework.

Configure a second runtime only in the private `.env` used by Compose:

```dotenv
LOCAL_OPENAI_BASE_URL=http://host.docker.internal:8080/v1
LOCAL_OPENAI_API_KEY=
LOCAL_OPENAI_PROVIDER_NAME=llama.cpp
ALLOW_PUBLIC_MODEL_ENDPOINTS=false
```

Public model endpoints are rejected by default. Accepted defaults are
loopback, private/link-local IP addresses, `host.docker.internal`, and
single-label Docker service names. This lets a Hugging Face model be used after
the owner has explicitly downloaded it and loaded it into a compatible local
runtime. The framework does not yet download or license-check Hugging Face
artifacts itself, and Ollama is still required for document embeddings.

## Recommended setup: Tailscale Serve

Install Tailscale on the host and every phone or laptop that should connect.
Sign them into the same tailnet. Do not enable Tailscale Funnel: Serve is
private to the tailnet, while Funnel would publish a service to the internet.

Find the host's full Tailscale DNS name. It ends in `.ts.net` and is shown for
the device in the Tailscale application or admin console. Then add these
values to the private `.env` beside `docker-compose.yml`:

```dotenv
REMOTE_GATEWAY_SHARED_SECRET=<a new random value of at least 32 characters>
REMOTE_GATEWAY_TRANSPORT=tailscale_serve
REMOTE_GATEWAY_BIND_ADDRESS=127.0.0.1
REMOTE_GATEWAY_HOSTNAME=<this-host>.<this-tailnet>.ts.net
REMOTE_GATEWAY_PORT=8443
REMOTE_GATEWAY_CONTAINER_PORT=80
REMOTE_GATEWAY_PUBLIC_URL=https://<this-host>.<this-tailnet>.ts.net
```

Keep the angle-bracket examples out of the real values. The public URL has no
`:8443`: Tailscale provides standard HTTPS on port 443. The local gateway port
remains 8443 and is deliberately bound to `127.0.0.1`; do not replace that
address with the host's `100.x` Tailscale IP on macOS. Container port 80 is an
internal loopback hop; it is not exposed to the LAN or tailnet.

Rebuild the backend and start the optional gateway:

```bash
docker compose --profile remote up -d --build backend gateway
```

When the installation uses an external environment file, keep using its normal
`--env-file /absolute/path/to/.env` argument in that command.

On the host, ask Tailscale Serve to publish the loopback gateway privately:

```bash
tailscale serve --bg http://127.0.0.1:8443
tailscale serve status
```

Tailscale may ask once for permission to enable HTTPS for the tailnet. The
gateway remains unavailable to the public internet and no router ports need to
be opened.

Open the framework on the host, choose **Remote access**, then:

1. Open **Connection mode**. The question-mark button beside **Access from**
   shows prerequisites, `.env` examples, and start/stop commands for every
   mode.
2. Select **Private VPN — Tailscale**, and apply it.
3. Open **Device keys**, name the device, select the minimum required domains,
   and create the key.
4. Copy the key immediately. It cannot be displayed again.
5. Open **Connect a device** to copy the API base URL and test gateway status.

The client needs Tailscale and its one-time framework device key. It does not
need the framework's Caddy CA certificate because Tailscale Serve supplies a
trusted certificate for the `.ts.net` address.

## Direct local-network alternative

The older direct transport remains available for an explicitly configured LAN
installation. Set `REMOTE_GATEWAY_TRANSPORT=direct`, use one exact private LAN
address as the bind address, set `REMOTE_GATEWAY_CONTAINER_PORT=443`, and
include `:8443` in the hostname URL. Direct mode uses Caddy's private CA, so
each client must install the downloadable CA certificate. Tailscale Serve is
preferred when access should work consistently across macOS, Linux, Windows,
phones, and networks.

## Stopping access

Set the UI mode to **Off**. The backend rejects new remote calls immediately,
even if the gateway container is still running. To stop the gateway process as
well:

```bash
tailscale serve --https=443 off
docker compose --profile remote stop gateway
```

Do not expose ports 3000, 8000, 5432, or 11434 to another network. Do not use
router port forwarding for port 8443, and do not advertise this gateway on the
public internet.

## Verified behavior and remaining release checks

The automated backend suite verifies Off mode, separate one-time device keys,
hash-only persistence, gateway authentication, domain filtering, unauthorized
domain concealment, stateless requests, JSON completions, SSE completion,
prompt-boundary handling, revocation, and generic local runtime endpoint
protection/stream translation. The frontend production build and both Compose
profiles validate successfully.

A live macOS Docker check additionally verified loopback TLS, `/health`, fixed
route denial, Off-mode rejection through Caddy, and that gateway logs contain
neither the test bearer token nor the test prompt body. A live Tailscale Serve
check also verified trusted `.ts.net` HTTPS routing to the loopback-only Caddy
gateway. The following release acceptance checks remain:

- a second physical device over LAN;
- Tailscale reachability and disconnect/reconnect behavior from a second device;
- host firewall guidance and detection;
- Windows and Linux gateway behavior;
- disconnect/reconnect and key-revocation checks from clean client devices; and
- signed/notarized installer distribution.

Until those checks pass, treat this subsystem as an implementation preview and
keep the default Off mode for ordinary use.
