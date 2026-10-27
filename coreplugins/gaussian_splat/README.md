# Gaussian Splat Plugin

This plugin trains a `gaussian_splat.ply` asset for completed WebODM tasks by calling an OpenSplat-compatible trainer.

Completed splats can be opened directly from the dashboard with **View Splat**.
The full-screen viewer is bundled locally using the MIT-licensed
`@playcanvas/supersplat-viewer`; it streams the authenticated PLY from WebODM
and provides orbit, fly, frame, quality, and fullscreen controls without
uploading the result to an external service.

WebODM/OpenSfM splats are stored Z-up. The bundled viewer maps +Z to its +Y
axis and starts from an elevated oblique camera, so aerial reconstructions open
with the ground horizontal and the vertical axis upright.

The default command is:

```bash
opensplat {input} -n {iterations} -o {output}
```

The repository Docker image builds a pinned CUDA-enabled OpenSplat binary and
the default Compose worker exposes the NVIDIA GPU to it. For non-Docker
deployments, install OpenSplat in the worker path or set
`GAUSSIAN_SPLAT_TRAINER_COMMAND` to a custom command template. The template supports:

- `{input}`: prepared OpenSplat project input folder
- `{output}`: target `gaussian_splat.ply` path
- `{iterations}`: requested training iterations

Example:

```bash
GAUSSIAN_SPLAT_TRAINER_COMMAND="/opt/opensplat/bin/opensplat {input} -n {iterations} -o {output}"
```

The Docker worker defaults to a 2x image downscale to keep large image sets
within typical desktop RAM and VRAM limits. Override it when needed with
`GAUSSIAN_SPLAT_DOWNSCALE_FACTOR` (1 keeps the original resolution).

The plugin expects a completed task with OpenSfM reconstruction files. Use the `Gaussian Splat Source` preset for best results.

NodeODM's `/var/www/data` is stored in the `nodeodmdata` volume and mounted
read-only in the worker at `/var/www/data`. This lets the trainer use the
OpenSfM reconstruction that NodeODM keeps outside WebODM's normal downloaded
result archive. NodeODM deletes finished task data after its retention period
(48 hours by default), so the first training run copies `reconstruction.json`,
`camera_models.json`, and `reference_lla.json` into the task's own
`assets/opensfm` folder. Retraining then works without the NodeODM copy.
