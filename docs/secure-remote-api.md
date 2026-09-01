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

## Preparing the HTTPS gateway

Do not place secrets in this repository. Add these values to the private
`.env` file actually passed to Docker Compose:

```dotenv
REMOTE_GATEWAY_SHARED_SECRET=<a new random value of at least 32 characters>
REMOTE_GATEWAY_BIND_ADDRESS=<one exact private LAN or Tailscale IP on this host>
REMOTE_GATEWAY_HOSTNAME=<the hostname or IP the client will use>
REMOTE_GATEWAY_PORT=8443
REMOTE_GATEWAY_PUBLIC_URL=https://<same-hostname-or-ip>:8443
```

`0.0.0.0`, loopback, multicast, and public addresses are rejected for an
enabled mode. Local-network mode requires a private LAN address. Private-VPN
mode currently requires a Tailscale IPv4 address in `100.64.0.0/10` or a
Tailscale IPv6 address in `fd7a:115c:a1e0::/48`.

After editing the private environment file, rebuild the backend so it receives
the values and start the optional gateway profile:

```bash
docker compose --profile remote up -d --build backend gateway
```

When the installation uses an external environment file, keep using its normal
`--env-file /absolute/path/to/.env` argument in that command.

Open the framework, choose **Remote access**, then:

1. Open **Connection mode**, select Local network or Private VPN, and apply it.
2. Open **Device keys**, name the device, select the minimum required domains,
   and create the key.
3. Copy the key immediately. It cannot be displayed again.
4. Open **Connect a device** to copy the API base URL and test gateway status.

The Caddy internal CA certificate becomes downloadable from that panel after
the gateway starts. The client device must trust this CA before using the
HTTPS endpoint without certificate warnings. Only install the certificate on
devices you control, and remove that trust if the installation is retired.

## Tailscale guidance

Private VPN mode does not install or sign in to Tailscale. Install the official
Tailscale application on both devices and sign both into the same authorized
tailnet. Configure the gateway with the host's exact Tailscale IP and DNS name.
No router port forwarding or UPnP is used. Tailscale uses an external
coordination service, while model inference and framework storage stay on the
host.

## Stopping access

Set the UI mode to **Off**. The backend rejects new remote calls immediately,
even if the gateway container is still running. To stop the gateway process as
well:

```bash
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
neither the test bearer token nor the test prompt body. The following are not
yet release-verified:

- a second physical device over LAN;
- Tailscale reachability and disconnect/reconnect behavior;
- host firewall guidance and detection;
- Windows and Linux gateway behavior;
- clean-machine certificate installation; and
- signed/notarized installer distribution.

Until those checks pass, treat this subsystem as an implementation preview and
keep the default Off mode for ordinary use.
