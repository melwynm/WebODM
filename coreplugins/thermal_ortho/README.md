# Thermal Orthophoto Plugin

Builds a single-band Celsius GeoTIFF (`thermal_orthophoto.tif`) for a task
that was uploaded with both RGB and thermal frames, using the ODM RGB
orthophoto for extent, CRS and georeferencing. It runs automatically when a
task completes with both kinds of imagery, or on demand from the task's
**Generate Thermal** button.

## Input detection

Frames are classified by filename first (DJI dual-lens suffixes: `_W`, `_Z`,
`_V` are RGB, `_T` is thermal), then by metadata: FLIR Planck constants, a
`RawThermalImageType`, a DJI `ImageSource` of `InfraredCamera`, or a FLIR
make. The camera model alone is never used, because a Mavic 3T or H20T writes
the same `Model` tag into every lens's frames.

## Temperature decoding

| Source | Support |
| --- | --- |
| FLIR radiometric JPEG/TIFF (FLIR cameras, DJI Zenmuse XT) | Decoded from the embedded raw image and Planck constants. |
| Radiometric TIFF (for example a DJI Thermal Analysis Tool export) | Float values are used as Celsius; integer values are interpreted as deci-Kelvin, centi-Kelvin or deci-Celsius. Visual exports are refused. |
| DJI R-JPEG (M2EA, M3T, H20T/H20N, M30T) | Needs the DJI Thermal SDK. Set `THERMAL_DJI_IRP_COMMAND` on the worker, otherwise the frame is refused with a clear error rather than decoded as a visual image. |

`THERMAL_DJI_IRP_COMMAND` is either the path to the SDK's `dji_irp` sample
binary, in which case the plugin runs

```
dji_irp -s {input} -a measure -o {output} --measurefmt float32
```

or a full command template containing `{input}` and `{output}`. The command
must write row-major little-endian float32 Celsius values covering the whole
frame to `{output}`.

If the SDK is not available, process the thermal frames on their own as a
separate task with the `Thermal` preset: ODM decodes DJI R-JPEGs itself and
produces a properly reconstructed thermal orthophoto.

## Output

The output grid is the RGB orthophoto grid downsampled to the native thermal
ground resolution, so a 2 cm RGB orthophoto with 640x512 thermal frames
produces a thermal raster roughly 4 to 6 times coarser, not a full-resolution
copy. Each frame is reprojected only into the part of the grid it touches.

## Limitations

Frames are placed on a flat, north-up footprint estimated from GPS position,
altitude and field of view, then aligned to the matching RGB frame by
translation only. Heading, lens distortion and terrain are not modelled, so
the result is a georeferenced thermal mosaic for review, not a survey-grade
orthorectified product. Use the `Thermal` preset on a thermal-only task when
geometric accuracy matters.
