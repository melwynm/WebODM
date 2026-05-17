# Gaussian Splat Plugin

This plugin trains a `gaussian_splat.ply` asset for completed WebODM tasks by calling an OpenSplat-compatible trainer.

The default command is:

```bash
opensplat {input} -n {iterations} -o {output}
```

Install OpenSplat in the worker container path, or set `GAUSSIAN_SPLAT_TRAINER_COMMAND` to a custom command template. The template supports:

- `{input}`: prepared OpenSplat project input folder
- `{output}`: target `gaussian_splat.ply` path
- `{iterations}`: requested training iterations

Example:

```bash
GAUSSIAN_SPLAT_TRAINER_COMMAND="/opt/opensplat/opensplat {input} -n {iterations} -o {output}"
```

The plugin expects a completed task with OpenSfM reconstruction files. Use the `Gaussian Splat Source` preset for best results.
