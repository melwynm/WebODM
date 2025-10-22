# Installing Docker for WebODM Development

This guide walks through setting up a local Docker daemon on Debian/Ubuntu-based
systems so you can build and run WebODM containers from source. It also explains
common issues you might encounter when working in sandboxed or CI environments
where privileged kernel features are not available.

## 1. Install the Docker Engine packages

```bash
sudo apt-get update
sudo apt-get install -y docker.io
```

These commands install the community edition of Docker packaged by Ubuntu. If you
need a newer release, follow the [official Docker instructions](https://docs.docker.com/engine/install/ubuntu/).

After the packages are installed you should add your user to the `docker` group so
you can interact with the daemon without root:

```bash
sudo usermod -aG docker $USER
newgrp docker
```

## 2. Start the Docker daemon

On traditional servers the daemon is started via `systemd`:

```bash
sudo systemctl enable --now docker.service
```

In minimal containers or CI runners where `systemd` is not available you can launch
the daemon manually:

```bash
sudo dockerd --host=unix:///var/run/docker.sock
```

Keep this terminal open so you can monitor log output while the daemon is running.

## 3. Verify the installation

Open a new terminal and run:

```bash
docker info
docker run --rm hello-world
```

The `docker info` command should report details about the daemon, and the
`hello-world` container should print a success message.

## 4. Troubleshooting permission and networking errors

Certain environments (such as unprivileged containers provided by CI services) do
not allow Docker to load kernel modules or configure iptables rules. When this
happens you may see errors similar to:

- `failed to create NAT chain DOCKER: iptables v1.8.10 (nf_tables): Permission denied`
- `failed to mount overlay: operation not permitted`
- `Failed to create bridge docker0 via netlink: operation not permitted`

These failures indicate the host does not grant the capabilities Docker needs to
set up its networking stack or storage drivers. Potential mitigations include:

1. **Rootless Docker** – Follow the [rootless setup guide](https://docs.docker.com/engine/security/rootless/)
   to run the daemon in user space. Rootless mode avoids the need for privileged
   kernel access but requires newuidmap/newgidmap support and cannot expose ports
   below 1024.
2. **FUSE overlayfs** – Install [`fuse-overlayfs`](https://github.com/containers/fuse-overlayfs)
   and start `dockerd` with `--storage-driver=fuse-overlayfs` when the default
   overlay2 driver cannot be loaded.
3. **Disable networking features** – For purely local testing you can pass
   `--iptables=false --bridge=none` to `dockerd` to skip networking setup. This is
   only useful when containers communicate via `--network host` or when you do not
   need networking at all.
4. **Request elevated privileges** – On managed CI services you might need to
   switch to a Docker-capable runner (for example GitHub Actions' `ubuntu-latest`
   with the `docker` service enabled) or use a VM instead of a containerized
   environment.

If none of these options are possible you will not be able to run Docker-in-Docker.
In that case, consider building images using a remote Docker host or a cloud-based
CI provider that supports Docker.

## 5. Next steps for WebODM

Once Docker is running locally you can build and start WebODM using the
[`docker-compose.yml`](../docker-compose.yml) in the project root:

```bash
docker-compose build --no-cache
docker-compose up -d
```

See the [manual installation](../README.md#manual-installation-docker) instructions
for additional details about configuring processing nodes, enabling MicMac, and
troubleshooting WebODM-specific issues.
