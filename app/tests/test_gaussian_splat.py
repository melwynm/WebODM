import os
from pathlib import Path
import sys

from django.contrib.auth.models import User
from django.test import override_settings
from nodeodm import status_codes

from app.models import Project, Task
from app.tests.classes import BootTestCase
from app.tests.utils import clear_test_media_root
from coreplugins.gaussian_splat.gaussian_splat.tasks import train_gaussian_splat


class TestGaussianSplat(BootTestCase):
    def tearDown(self):
        clear_test_media_root()

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
        self.assertIn("gaussian_splat.ply", task.available_assets)
