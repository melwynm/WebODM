import os
from pathlib import Path
import sys

from django.contrib.auth.models import User
from django.test import override_settings
from nodeodm import status_codes

from app.models import Project, Task
from app.tests.classes import BootTestCase
from app.tests.utils import clear_test_media_root
from coreplugins.gaussian_splat.gaussian_splat.tasks import (
    _progress_from_line,
    build_status_payload,
    prepare_opensplat_input,
    train_gaussian_splat,
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
