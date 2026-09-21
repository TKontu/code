# Self-hosted GitHub Actions runner

A runner for jobs that need your LAN — here, `.github/workflows/devbox-image.yml`, which builds
`starters/devbox` and pushes it to a private registry GitHub's own runners cannot reach.

## Security — read before deploying

The runner mounts the host's Docker socket, so **any job it runs is root on that host.** On a
public repository that matters: for pull requests, GitHub runs the workflow files *from the PR*,
so a fork can add a job with `runs-on: self-hosted` and have it run here.

Before registering the runner:

1. **Settings → Actions → General → "Approval for running fork pull request workflows from
   contributors"** → *Require approval for all external contributors*. Then read every fork PR's
   workflow changes before approving a run.
2. Never add `pull_request` or `pull_request_target` to a workflow that targets this runner.
3. Prefer a host where root is an acceptable blast radius — ideally not one holding things you
   cannot rebuild. Making the repository private removes the fork risk entirely.

## Deploy

On the runner host:

1. If the registry is plain HTTP, allow it in the host's `/etc/docker/daemon.json` and restart
   Docker — jobs push through this daemon:
   ```json
   { "insecure-registries": ["<registry-host>:<port>"] }
   ```
2. Provide `REPO_URL` and `ACCESS_TOKEN` (see `.env.example`):
   - **docker compose** — copy `compose.yaml` and `.env.example` into a directory,
     `cp .env.example .env`, fill it in, `chmod 600 .env`, then `docker compose up -d`.
   - **Portainer** — paste `compose.yaml` as a stack and set the two variables under
     *Environment variables*.
3. Watch the logs until it prints *Listening for Jobs*. The runner appears under
   **Settings → Actions → Runners** as idle.

## Repository settings the devbox workflow reads

**Settings → Secrets and variables → Actions:**

| Kind | Name | Value |
| --- | --- | --- |
| Variable | `REGISTRY` | Registry `host:port` |
| Variable | `DEVBOX_IMAGE_NAME` | Path in the registry, e.g. `<owner>/devbox` |
| Variable | `DEVBOX_BASE_IMAGE` | Optional. A CUDA devel image for GPU hosts |
| Variable | `DEVBOX_TORCH_INDEX` | Optional. The matching torch wheel index |
| Secret | `REGISTRY_USERNAME` | Registry user |
| Secret | `REGISTRY_TOKEN` | Registry token with package write permission |

For a Gitea registry, create the token under **User settings → Applications** with the
`write:package` scope.

The workflow runs on pushes to `main` that touch `starters/devbox/`, and on demand from the Actions
tab (**Run workflow**). It pushes three tags: the UTC build date, `sha-<commit>`, and `latest`.
