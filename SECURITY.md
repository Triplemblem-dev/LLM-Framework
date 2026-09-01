# Security policy

## Supported version

Until tagged releases exist, security fixes target the current default branch.
This project is designed for trusted local or private-network operation and is
not yet hardened for multi-user or direct public-internet deployment.

## Reporting a vulnerability

Use GitHub's private vulnerability-reporting feature for the repository. Do not
open a public issue containing exploit details, access tokens, `.env` contents,
documents, prompts, memories, repository snapshots, database dumps, model
outputs, IP addresses, or other private installation data.

Include only the minimum information needed to reproduce the issue:

- affected commit or release;
- operating system and deployment mode;
- affected component and endpoint;
- reproduction steps using synthetic data;
- expected and observed security boundary; and
- suggested mitigation, if known.

If private vulnerability reporting is not enabled, ask the maintainer through a
public issue to enable a private reporting channel without disclosing the
vulnerability itself.

## Deployment expectations

- Keep `.env` and its backups private and out of version control.
- Do not publish ports 3000 or 8000 directly to the internet.
- Leave Remote Access in Off mode unless the optional HTTPS gateway has been
  deliberately configured. Never expose the gateway through router port
  forwarding or UPnP.
- Use a separate revocable device key for each remote client; never give a
  remote client the internal `APP_ACCESS_TOKEN`.
- Do not mount the Docker socket into backend or frontend containers.
- Treat uploaded documents, repositories, and retrieved content as untrusted.
- Back up database and storage volumes before upgrades or destructive changes.
- Use only launcher artifacts obtained from this repository's releases and
  verify published checksums once signed releases are available.

The setup launcher may install host prerequisites only after explicit local
confirmation. It is not remotely callable and must never be exposed as a model
tool or backend administration API.
