# Examples

## 1. Authenticate and inspect projects

1. Call webodm_authenticate with your username and password.
2. Call webodm_list_projects.
3. Call webodm_get_project for the project you care about.

## 2. Find completed tasks in a project

1. Call webodm_list_tasks with:

```json
{
  "project_id": 1,
  "query": {
    "status": 40,
    "ordering": "-created_at"
  }
}
```

2. Inspect each task with webodm_get_task.

## 3. Create a new task from local images

```json
{
  "project_id": 1,
  "image_paths": [
    "C:/data/images/IMG_0001.JPG",
    "C:/data/images/IMG_0002.JPG"
  ],
  "name": "North field survey",
  "options": [
    { "name": "orthophoto-resolution", "value": 3 },
    { "name": "use-opensfm-pointcloud", "value": true }
  ]
}
```

## 4. Use the partial upload workflow

1. Create the placeholder:

```json
{
  "project_id": 1,
  "payload": {
    "name": "Large upload task"
  }
}
```

2. Upload files with webodm_upload_task_files.
3. Finalize with webodm_commit_task_upload.

## 5. Get incremental task output

```json
{
  "project_id": 1,
  "task_id": 42,
  "query": {
    "line": 100,
    "f": "text"
  }
}
```

## 6. Request a raster export

```json
{
  "project_id": 1,
  "task_id": 42,
  "asset_type": "orthophoto",
  "payload": {
    "format": "png",
    "formula": "NDVI",
    "bands": "RGN",
    "color_map": "rdylgn",
    "rescale": "-1,1"
  }
}
```

If WebODM returns a celery_task_id, poll it with webodm_check_worker_task.

## 7. Build a direct authenticated asset URL

```json
{
  "project_id": 1,
  "task_id": 42,
  "asset": "all.zip",
  "include_jwt_query": true
}
```

## 8. Start a monitoring comparison

1. Call webodm_get_monitoring_candidates.
2. Choose a candidate task ID.
3. Call webodm_create_monitoring_compare with compare_task set to that task ID.
