# gs Container Deployment

`gs` can be shipped as a container image so deployment no longer depends on the host's `glibc` version.

This mode is recommended for:

- remote Linux servers
- mixed Linux distributions
- Windows hosts running Docker Desktop or Podman Desktop
- release artifacts that should behave the same everywhere

The default base image is now an ECR public mirror of the Python official image so builds are less dependent on Docker Hub reachability.

## Runtime behavior

The container does not introduce a second implementation path.

It starts the same launcher used by the packaged binary:

- `python -m genesis.packaged_cli`
- which in turn calls the current `genesis.main`

That means command surface and behavior stay aligned with the existing Python/native flow.

## Persistent state

All mutable state is stored under `/var/lib/gs` inside the container:

- `/var/lib/gs/config.yaml`
- `/var/lib/gs/data/chain.db`
- `/var/lib/gs/data/chronicle/`
- `/var/lib/gs/data/commands/`
- `/var/lib/gs/data/mobile/`

The default container flow mounts `/var/lib/gs` to a named volume, so restarting or recreating the container will not lose blockchain data.

You only lose data if you delete the backing volume or host directory yourself.

## Option 1: Compose

Build and start:

```bash
docker compose -f docker/gs/compose.yaml up --build -d
```

If you need to override the base image or pip mirror:

```bash
GS_PYTHON_BASE_IMAGE=public.ecr.aws/docker/library/python:3.11-slim-bookworm \
GS_APT_MIRROR_URL=https://mirrors.tuna.tsinghua.edu.cn \
GS_PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
docker compose -f docker/gs/compose.yaml up --build -d
```

View logs:

```bash
docker compose -f docker/gs/compose.yaml logs -f
```

Run commands inside the container:

```bash
docker compose -f docker/gs/compose.yaml exec gs gs status
docker compose -f docker/gs/compose.yaml exec gs gs task "your task"
docker compose -f docker/gs/compose.yaml exec gs gs lang zh
```

Stop and remove the container:

```bash
docker compose -f docker/gs/compose.yaml down
```

`down` removes the container, but it does not delete the named state volume.

Default exposed ports:

- `19840/udp` -> discovery
- `19841/tcp` -> P2P
- `19842/tcp` -> optional WebSocket API

Default state volume in compose mode:

- `genesis-gs-state`

Override the volume name when deploying to a server:

```bash
GS_STATE_VOLUME=gs-prod-state docker compose -f docker/gs/compose.yaml up --build -d
```

## Option 2: Helper script

For Linux hosts, the wrapper script gives `gs`-style subcommands:

```bash
bash scripts/build_latest_gs_image.sh
bash scripts/gs_container.sh build
bash scripts/gs_container.sh load dist/genesis-gs_latest.tar
bash scripts/gs_container.sh start
bash scripts/gs_container.sh status
bash scripts/gs_container.sh task "hello"
bash scripts/gs_container.sh logs
bash scripts/gs_container.sh stop
```

When Python code changes and you just want the newest image again, the recommended one-command rebuild is:

```bash
bash scripts/build_latest_gs_image.sh
```

If you want the newest image plus a fresh offline deployment bundle in one run:

```bash
bash scripts/build_latest_gs_image.sh --bundle
```

Useful overrides:

```bash
GS_STATE_VOLUME=gs-prod-state bash scripts/gs_container.sh start
GS_HOST_STATE_DIR=/srv/gs bash scripts/gs_container.sh start
GS_IMAGE_TAG=my-registry/gs:latest bash scripts/gs_container.sh build
GS_USE_HOST_NETWORK=true bash scripts/gs_container.sh start
GS_ENABLE_API=true bash scripts/gs_container.sh start
GS_APT_MIRROR_URL=https://mirrors.tuna.tsinghua.edu.cn bash scripts/gs_container.sh build
GS_PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple bash scripts/gs_container.sh build
GS_APT_MIRROR_URL=https://mirrors.tuna.tsinghua.edu.cn GS_PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple bash scripts/build_latest_gs_image.sh --bundle
```

The helper script uses a named volume by default. If you set `GS_HOST_STATE_DIR`, it switches to a bind mount and adds the `:Z` relabel option automatically for Podman.

The helper script removes the container on `stop`, but it keeps the state volume or host state directory intact.

## Option 3: Offline bundle for a remote server

If the target server cannot reliably pull from public registries, build an offline bundle on a machine that can build locally:

```bash
bash scripts/build_gs_container_bundle.sh
```

If you are in China and want explicit mirrors during bundle creation:

```bash
GS_PYTHON_BASE_IMAGE=public.ecr.aws/docker/library/python:3.11-slim-bookworm \
GS_APT_MIRROR_URL=https://mirrors.tuna.tsinghua.edu.cn \
GS_PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
bash scripts/build_gs_container_bundle.sh
```

This produces:

- `dist/genesis-gs-container-bundle.tar.gz`
- `dist/genesis-gs-container-bundle.tar.gz.sha256`

Copy that single tarball to the target server, then:

```bash
tar -xzf genesis-gs-container-bundle.tar.gz
cd genesis-gs-container-bundle
bash install.sh
```

The bundle installer:

- loads the embedded image tar into Docker or Podman
- writes `.gs_container.env` next to the extracted scripts so later commands reuse the same engine and ports
- starts `gs` with the default named volume unless you explicitly pass `GS_HOST_STATE_DIR=/srv/gs`

After install, the target server can use:

```bash
bash gs_container.sh status
bash gs_container.sh logs
bash gs_container.sh stop
bash gs_container.sh start
```

If you want host-directory storage instead of a named volume during install:

```bash
GS_HOST_STATE_DIR=/srv/gs bash install.sh
```

## Option 4: Export raw image tar for a remote server

Build and save:

```bash
bash scripts/gs_container.sh build
bash scripts/gs_container.sh save
```

Default archive output:

```bash
dist/genesis-gs_latest.tar
```

On the target server:

```bash
docker load -i dist/genesis-gs_latest.tar
docker run -d \
  --name genesis-gs \
  --restart unless-stopped \
  -v genesis-gs-state:/var/lib/gs \
  -p 19840:19840/udp \
  -p 19841:19841/tcp \
  -p 19842:19842/tcp \
  genesis-gs:latest
```

Operational commands:

```bash
docker exec -it genesis-gs gs status
docker exec -it genesis-gs gs task "your task"
docker exec -it genesis-gs gs lang zh
docker logs -f genesis-gs
docker stop genesis-gs
docker rm genesis-gs
```

Again, removing the container does not remove `genesis-gs-state`.

If you explicitly want a host directory instead of a named volume:

```bash
docker run -d \
  --name genesis-gs \
  --restart unless-stopped \
  -v /srv/gs:/var/lib/gs \
  -p 19840:19840/udp \
  -p 19841:19841/tcp \
  genesis-gs:latest
```

For Podman on SELinux hosts, use:

```bash
podman run -d \
  --name genesis-gs \
  --restart unless-stopped \
  -v /srv/gs:/var/lib/gs:Z \
  -p 19840:19840/udp \
  -p 19841:19841/tcp \
  genesis-gs:latest
```

## Public node deployment

If the host has a real public IP or a public domain that resolves to it, the containerized `gs` can still serve as a public node for other peers.

The key requirements are:

- inbound `19841/tcp` must reach the container
- host firewall / cloud security group must allow the traffic
- `gs` must be able to auto-detect the host's public IP and verify reachability

How address publishing works now:

- when `network.advertise_address` is empty, `gs` auto-detects the public IP using multiple external IP services
- it then performs a lightweight self-probe against `public_ip:listen_port`
- verified public IPs are preferred for the on-chain endpoint/contact card
- this avoids asking non-technical users to manually configure a public IP in normal deployments

`advertise_address` is now an override, not the normal path.

Only set it manually if:

- the server is behind an unusual reverse path
- you want to publish a public domain instead of the raw IP
- your environment blocks external IP discovery services

Optional override example:

```yaml
network:
  listen_port: 19841
  discovery_port: 19840
  advertise_address: "your.public.ip.or.domain"
```

Recommended Linux run command for a public node:

```bash
docker run -d \
  --name genesis-gs \
  --restart unless-stopped \
  -v genesis-gs-state:/var/lib/gs \
  -p 19840:19840/udp \
  -p 19841:19841/tcp \
  genesis-gs:latest
```

On Linux, host networking is also acceptable when you want the container to behave more like a native service:

```bash
GS_USE_HOST_NETWORK=true bash scripts/gs_container.sh start
```

With correct inbound reachability, the node can still publish a usable contact card and be dialed by other `gs` nodes.

## LLM endpoint note

If your model endpoint runs on the host machine:

- Docker Desktop on Windows/macOS: set `llm.base_url` to `http://host.docker.internal:11434/v1`
- Docker on Linux: use `host.docker.internal` with the provided compose/helper settings, or start with host networking

If the model endpoint is remote, set the normal remote URL in `/var/lib/gs/config.yaml`.

## Optional API server

To keep behavior aligned with the current native start flow, the container does not enable the WebSocket API by default.

Enable it explicitly when needed:

```bash
GS_ENABLE_API=true docker compose -f docker/gs/compose.yaml up --build -d
```

or:

```bash
GS_ENABLE_API=true bash scripts/gs_container.sh start
```
