from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import sys
from unittest import mock

from django.contrib.auth.models import User
from django.test import override_settings
from nodeodm import status_codes

from app.models import Preset, Project, Task
from app.tests.classes import BootTestCase
from app.tests.utils import clear_test_media_root
from coreplugins.gaussian_splat.gaussian_splat.tasks import (
    _progress_from_line,
    build_status_payload,
    enqueue_gaussian_splat,
    prepare_opensplat_input,
    run_gaussian_splat,
    train_gaussian_splat,
    write_job_status,
)


class TestGaussianSplat(BootTestCase):
    def tearDown(self):
        clear_test_media_root()

    def test_opensplat_progress_formats(self):
        self.assertEqual(_progress_from_line("Step 760: 0.112498 [2%]", 30000), 11)
        self.assertEqual(_progress_from_line("Step 30000: 0.09 [100%]", 30000), 95)
        self.assertEqual(_progress_from_line("iteration 15000 / 30000", 30000), 52)
        self.assertIsNone(_progress_from_line("Culled 48750 gaussians", 30000))

    def test_unqueued_task_reports_idle_status(self):
        user = User.objects.get(username="testuser")
        project = Project.objects.create(owner=user, name="Idle Splat Project")
        task = Task.objects.create(
            project=project,
            name="Idle Splat Task",
            status=status_codes.COMPLETED,
        )

        status = build_status_payload(task)

        self.assertEqual(status["status"], "idle")
        self.assertEqual(status["progress"], 0)
        self.assertIsNone(status["celery_task_id"])

    def test_source_preset_keeps_dense_and_mesh_settings_light(self):
        preset = Preset.objects.get(name="Gaussian Splat Source", system=True)
        options = {option["name"]: option["value"] for option in preset.options}

        # Splat training uses only the sparse reconstruction; ultra point
        # clouds and deep meshes ran out of memory on a 16 GB host.
        self.assertEqual(options["feature-quality"], "ultra")
        self.assertNotIn("pc-quality", options)
        self.assertNotIn("mesh-octree-depth", options)
        self.assertNotIn("mesh-size", options)
        self.assertNotIn("use-3dmesh", options)

    def test_stale_running_job_can_be_requeued(self):
        user = User.objects.get(username="testuser")
        project = Project.objects.create(owner=user, name="Stale Splat Project")
        task = Task.objects.create(
            project=project,
            name="Stale Splat Task",
            status=status_codes.COMPLETED,
        )
        write_job_status(task, {"status": "running", "celery_task_id": "lost-job"})

        with mock.patch.object(run_gaussian_splat, "delay") as delay:
            delay.return_value = mock.Mock(id="live-job")
            result = enqueue_gaussian_splat(task)
            self.assertEqual(result.celery_task_id, "lost-job")
            delay.assert_not_called()

            stale = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            status_path = Path(task.data_path("gaussian_splat_status.json"))
            stored = json.loads(status_path.read_text(encoding="utf-8"))
            stored["updated_at"] = stale
            status_path.write_text(json.dumps(stored), encoding="utf-8")

            result = enqueue_gaussian_splat(task)

        self.assertEqual(result.celery_task_id, "live-job")
        self.assertEqual(build_status_payload(task)["status"], "pending")

    def test_trainer_command_writes_gaussian_splat_asset(self):
        user = User.objects.get(username="testuser")
        project = Project.objects.create(owner=user, name="Splat Project")
        task = Task.objects.create(project=project, name="Splat Task", status=status_codes.COMPLETED)

        Path(task.task_path()).mkdir(parents=True, exist_ok=True)
        Path(task.task_path("image_001.jpg")).write_bytes(b"fake image")

        opensfm_dir = Path(task.assets_path("opensfm"))
        opensfm_dir.mkdir(parents=True, exist_ok=True)
        (opensfm_dir / "reconstruction.json").write_text("[]", encoding="utf-8")

        script = Path(task.task_path("fake_opensplat.py"))
        script.write_text(
            "import sys\n"
            "from pathlib import Path\n"
            "out = Path(sys.argv[sys.argv.index('-o') + 1])\n"
            "print('iteration 1/2')\n"
            "out.write_text('ply\\n', encoding='utf-8')\n",
            encoding="utf-8",
        )

        command = "{} {} {{input}} -n {{iterations}} -o {{output}}".format(sys.executable, script)
        with override_settings():
            previous = os.environ.get("GAUSSIAN_SPLAT_TRAINER_COMMAND")
            os.environ["GAUSSIAN_SPLAT_TRAINER_COMMAND"] = command
            try:
                result = train_gaussian_splat(task, {"iterations": 200, "force": True})
            finally:
                if previous is None:
                    os.environ.pop("GAUSSIAN_SPLAT_TRAINER_COMMAND", None)
                else:
                    os.environ["GAUSSIAN_SPLAT_TRAINER_COMMAND"] = previous

        task.refresh_from_db()
        self.assertTrue(Path(result["output"]).is_file())
        self.assertEqual(result["downscale_factor"], 2)
        self.assertIn("gaussian_splat.ply", task.available_assets)

    def test_uses_opensfm_from_shared_nodeodm_data(self):
        user = User.objects.get(username="testuser")
        project = Project.objects.create(owner=user, name="Shared OpenSfM Project")
        task = Task.objects.create(
            project=project,
            name="Shared OpenSfM Task",
            status=status_codes.COMPLETED,
        )

        Path(task.task_path()).mkdir(parents=True, exist_ok=True)
        Path(task.task_path("image_001.jpg")).write_bytes(b"fake image")

        shared_root = Path(task.task_path("shared-nodeodm"))
        opensfm_dir = shared_root / str(task.uuid) / "opensfm"
        opensfm_dir.mkdir(parents=True, exist_ok=True)
        (opensfm_dir / "reconstruction.json").write_text("[]", encoding="utf-8")

        previous = os.environ.get("GAUSSIAN_SPLAT_NODEODM_DATA_ROOT")
        os.environ["GAUSSIAN_SPLAT_NODEODM_DATA_ROOT"] = str(shared_root)
        try:
            input_dir = prepare_opensplat_input(task)
        finally:
            if previous is None:
                os.environ.pop("GAUSSIAN_SPLAT_NODEODM_DATA_ROOT", None)
            else:
                os.environ["GAUSSIAN_SPLAT_NODEODM_DATA_ROOT"] = previous

        self.assertTrue((input_dir / "reconstruction.json").is_file())
        self.assertTrue((input_dir / "images" / "image_001.jpg").is_file())
        image_list = (input_dir / "image_list.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(image_list, [str(input_dir / "image_001.jpg")])
        self.assertTrue(Path(task.assets_path("opensfm", "reconstruction.json")).is_file())

    def test_retraining_survives_nodeodm_cleanup(self):
        user = User.objects.get(username="testuser")
        project = Project.objects.create(owner=user, name="Cleaned OpenSfM Project")
        task = Task.objects.create(
            project=project,
            name="Cleaned OpenSfM Task",
            status=status_codes.COMPLETED,
        )

        Path(task.task_path()).mkdir(parents=True, exist_ok=True)
        Path(task.task_path("image_001.jpg")).write_bytes(b"fake image")

        shared_root = Path(task.task_path("shared-nodeodm"))
        opensfm_dir = shared_root / str(task.uuid) / "opensfm"
        opensfm_dir.mkdir(parents=True, exist_ok=True)
        (opensfm_dir / "reconstruction.json").write_text("[]", encoding="utf-8")

        # Simulate a link left by an earlier run into NodeODM's volume.
        input_dir = Path(task.assets_path("odm_gaussian_splat", "opensplat_input"))
        input_dir.mkdir(parents=True, exist_ok=True)
        (input_dir / "reconstruction.json").symlink_to(opensfm_dir / "reconstruction.json")

        previous = os.environ.get("GAUSSIAN_SPLAT_NODEODM_DATA_ROOT")
        os.environ["GAUSSIAN_SPLAT_NODEODM_DATA_ROOT"] = str(shared_root)
        try:
            prepare_opensplat_input(task)
            shutil.rmtree(shared_root)
            input_dir = prepare_opensplat_input(task)
        finally:
            if previous is None:
                os.environ.pop("GAUSSIAN_SPLAT_NODEODM_DATA_ROOT", None)
            else:
                os.environ["GAUSSIAN_SPLAT_NODEODM_DATA_ROOT"] = previous

        self.assertEqual((input_dir / "reconstruction.json").read_text(encoding="utf-8"), "[]")
        self.assertTrue((input_dir / "opensfm" / "reconstruction.json").is_file())
