import os


OUTPUT_DIRNAME = "odm_gaussian_splat"
OUTPUT_FILENAME = "gaussian_splat.ply"
STATUS_FILE = "gaussian_splat_status.json"
DEFAULT_ITERATIONS = int(os.environ.get("GAUSSIAN_SPLAT_DEFAULT_ITERATIONS", "7000"))
TRAINER_COMMAND_ENV = "GAUSSIAN_SPLAT_TRAINER_COMMAND"

