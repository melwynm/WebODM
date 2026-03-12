# Troubleshooting

## Authentication fails

- Verify the WebODM URL is correct.
- Confirm you are using a real WebODM username and password.
- This fork expects Bearer tokens for API calls after authentication.

## Signature has expired

WebODM access tokens expire after the configured SIMPLE_JWT lifetime. Authenticate again with webodm_authenticate.

## Project list shape looks different than expected

This fork disables pagination when page is not provided. That means /api/projects/ may return a plain array, while /api/projects/?page=1 returns a paginated object.

## Task creation says you need at least 2 images

The direct create-task endpoint requires two or more files. If you need to stage files first, use the partial task workflow:

1. webodm_create_partial_task
2. webodm_upload_task_files
3. webodm_commit_task_upload

## Download URLs do not work outside the MCP client

Use include_jwt_query=true when building the URL, or pass an Authorization: Bearer <token> header manually.

## Import from URL fails

The import endpoint only accepts http or https URLs for remote imports. If you have a local zip file, use webodm_import_task_from_archive instead.

## Export returns a celery_task_id instead of a file URL

That is normal when WebODM needs to render or transform the output. Poll the celery ID with webodm_check_worker_task. Once ready, use webodm_get_worker_result_url.

## Syntax check passes but runtime fails

npm run smoke only checks syntax. You still need npm install and a live WebODM instance for end-to-end validation.
