# Deer Detection Validation

Last updated: 2026-06-01

## Current Status

Deer detection is technically implemented and covered by regression tests. It is not yet commercially validated as a wildlife count because this repository does not include a real deer orthomosaic or thermal drone sample.

## Implemented Path

- UI model option: `Deer`
- Backend model key: `deer`
- Detection class filter: `deer`
- Size filter: 0.8m to 2.4m long side, scaled by orthophoto GSD
- Count source: the object detection map layer feature count
- Review path: detections can be downloaded as GeoJSON or promoted to review issues

## Technical Validation

Run these checks after code changes:

```bash
python manage.py check
python manage.py test app.tests.test_objdetect --keepdb
python manage.py rebuildplugins
```

Expected results:

- Django check reports no issues.
- Object detection tests pass.
- Plugin rebuild regenerates the object detection frontend bundle with the `Deer` option.

## Field Validation Requirement

Before selling deer counting as a commercial deliverable, validate against real imagery:

1. Use at least one RGB orthomosaic or thermal orthomosaic with visible deer.
2. Record flight altitude, camera type, GSD, date, habitat, and expected/manual count.
3. Run object detection with the `Deer` model.
4. Compare AI count to manual review count.
5. Record false positives, missed animals, confidence threshold, GSD, and size-filter behavior.
6. Repeat until the acceptable error band is known for the service package.

Suggested acceptance gate for a pilot:

- Manual review of all detections completed.
- False positives and missed deer recorded.
- Count is presented as reviewed candidate count, not an official population census.
- Commercial report includes AI/object-detection caveats.

## Candidate Specialized Sources

The current implementation uses the generic YOLO class path. For a stronger wildlife product, evaluate a specialized aerial wildlife model:

- BAMBI Detection Dataset: https://zenodo.org/records/15773102
- BAMBI model weights: https://huggingface.co/cpraschl/bambi-models
- YOLO thermal aerial wildlife research: https://www.mdpi.com/2504-446X/8/1/2

## Repository Check On 2026-06-01

Local repository imagery was searched for `.tif`, `.tiff`, `.jpg`, `.jpeg`, `.png`, `.onnx`, `.pt`, and `.weights` files. No real deer validation imagery or specialized deer model weights were present in the workspace.
