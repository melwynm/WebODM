import os
import tempfile

from django.core.exceptions import SuspiciousFileOperation
from django.test import SimpleTestCase

from app.security import path_traversal_check


class PathTraversalCheckTests(SimpleTestCase):
    def test_accepts_path_within_known_safe_directory(self):
        with tempfile.TemporaryDirectory() as root:
            known_safe_path = os.path.join(root, "safe", "1")
            os.makedirs(known_safe_path)

            target_path = os.path.join(known_safe_path, "child", "file.txt")

            self.assertEqual(
                path_traversal_check(target_path, known_safe_path),
                os.path.realpath(target_path),
            )

    def test_rejects_sibling_directory(self):
        with tempfile.TemporaryDirectory() as root:
            known_safe_path = os.path.join(root, "safe", "1")
            os.makedirs(known_safe_path)

            sibling_path = os.path.join(root, "safe", "11", "child.txt")
            os.makedirs(os.path.dirname(sibling_path))

            with self.assertRaises(SuspiciousFileOperation):
                path_traversal_check(sibling_path, known_safe_path)

    def test_rejects_parent_directory_traversal(self):
        with tempfile.TemporaryDirectory() as root:
            known_safe_path = os.path.join(root, "safe", "1")
            os.makedirs(known_safe_path)

            traversal_path = os.path.join(known_safe_path, os.pardir, "2", "child.txt")

            with self.assertRaises(SuspiciousFileOperation):
                path_traversal_check(traversal_path, known_safe_path)
