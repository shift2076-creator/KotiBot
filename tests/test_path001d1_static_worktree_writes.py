import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.path001d1_static_worktree_writes import (
    LAUNCH_TAINT,
    RELATIVE_RUNTIME_TAINT,
    SOURCE_TAINT,
    render_summary,
    scan_python_source,
    scan_repository,
)


class Path001D1StaticWorktreeWriteTests(unittest.TestCase):
    def test_source_relative_read_is_not_a_writer_violation(self):
        writers, subprocesses = scan_python_source(
            """
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
text = (BASE_DIR / "requirements.txt").read_text()
""",
            "module.py",
        )

        self.assertEqual(writers, [])
        self.assertEqual(subprocesses, [])

    def test_source_derived_writer_is_blocked(self):
        writers, _ = scan_python_source(
            """
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "state.json"
STATE_FILE.write_text("{}")
""",
            "module.py",
        )

        self.assertEqual(len(writers), 1)
        self.assertEqual(writers[0].origin, SOURCE_TAINT)

    def test_function_local_source_taint_propagates(self):
        writers, _ = scan_python_source(
            """
from pathlib import Path
def save():
    root = Path(__file__).resolve().parent
    target = root / "state.json"
    target.write_text("{}")
""",
            "module.py",
        )

        self.assertEqual(len(writers), 1)
        self.assertEqual(writers[0].origin, SOURCE_TAINT)

    def test_attribute_source_taint_propagates(self):
        writers, _ = scan_python_source(
            """
from pathlib import Path
class Store:
    def save(self):
        self.root = Path(__file__).resolve().parent
        self.target = self.root / "state.json"
        self.target.write_text("{}")
""",
            "module.py",
        )

        self.assertEqual(len(writers), 1)
        self.assertEqual(writers[0].origin, SOURCE_TAINT)

    def test_launch_directory_writer_is_blocked(self):
        writers, _ = scan_python_source(
            """
from pathlib import Path
root = Path.cwd()
(root / "cache" / "item.tmp").write_bytes(b"x")
""",
            "module.py",
        )

        self.assertEqual(len(writers), 1)
        self.assertEqual(writers[0].origin, LAUNCH_TAINT)

    def test_relative_runtime_literal_writer_is_blocked(self):
        writers, _ = scan_python_source(
            """
from pathlib import Path
Path("state.json").write_text("{}")
""",
            "module.py",
        )

        self.assertEqual(len(writers), 1)
        self.assertEqual(
            writers[0].origin,
            LAUNCH_TAINT,
        )

    def test_runtime_path_resolver_writer_is_classified_safe(self):
        writers, _ = scan_python_source(
            """
def save(paths, encoded):
    paths.server_state_file.write_text(encoded)
""",
            "module.py",
        )

        self.assertEqual(len(writers), 1)
        self.assertEqual(
            writers[0].origin,
            "runtime-path-resolver",
        )

    def test_atomic_writer_path_is_inventoried(self):
        writers, _ = scan_python_source(
            """
def save(state_file, data):
    write_json_atomic_sync(state_file, data)
""",
            "module.py",
        )

        self.assertEqual(len(writers), 1)
        self.assertEqual(writers[0].origin, "path-variable")

    def test_subprocess_cwd_from_source_tree_is_blocked(self):
        _, subprocesses = scan_python_source(
            """
from pathlib import Path
import subprocess
BASE_DIR = Path(__file__).resolve().parent
subprocess.run(["tool"], cwd=BASE_DIR)
""",
            "module.py",
        )

        self.assertEqual(len(subprocesses), 1)
        self.assertEqual(
            subprocesses[0].origin,
            SOURCE_TAINT,
        )

    def test_string_replace_is_not_a_filesystem_writer(self):
        writers, _ = scan_python_source(
            """
def render(stylesheet):
    return stylesheet.replace("old", "new")
""",
            "module.py",
        )

        self.assertEqual(writers, [])

    def test_domain_remove_method_is_not_a_filesystem_writer(self):
        writers, _ = scan_python_source(
            """
def remove(store, device_id):
    store.remove(device_id)
""",
            "module.py",
        )

        self.assertEqual(writers, [])

    def test_os_remove_is_a_filesystem_writer(self):
        writers, _ = scan_python_source(
            """
import os
def remove(path):
    os.remove(path)
""",
            "module.py",
        )

        self.assertEqual(len(writers), 1)
        self.assertEqual(writers[0].kind, "remove")
        self.assertEqual(writers[0].origin, "path-variable")

    def test_path_replace_is_still_inventoried(self):
        writers, _ = scan_python_source(
            """
def replace(tmp_path, path):
    tmp_path.replace(path)
""",
            "module.py",
        )

        self.assertEqual(len(writers), 2)
        self.assertTrue(
            all(site.kind == "replace" for site in writers)
        )
        self.assertTrue(
            all(site.origin == "path-variable" for site in writers)
        )

    def test_runtime_filename_join_does_not_taint_subprocess(self):
        _, subprocesses = scan_python_source(
            """
import subprocess
def launch(stream_dir):
    segment_pattern = stream_dir / "seg_%05d.ts"
    playlist = stream_dir / "index.m3u8"
    cmd = [
        "ffmpeg",
        "-hls_segment_filename",
        str(segment_pattern),
        str(playlist),
    ]
    subprocess.Popen(cmd)
""",
            "module.py",
        )

        self.assertEqual(len(subprocesses), 1)
        self.assertNotEqual(
            subprocesses[0].origin,
            RELATIVE_RUNTIME_TAINT,
        )

    def test_repository_scan_excludes_tools_tests_and_docs(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "server_core").mkdir()
            (root / "tools").mkdir()
            (root / "tests").mkdir()
            (root / "docs").mkdir()

            (root / "server_core" / "state.py").write_text(
                """
def save(paths, data):
    paths.server_state_file.write_text(data)
""",
                encoding="utf-8",
            )
            (root / "tools" / "helper.py").write_text(
                'open("tool.log", "w").write("x")\n',
                encoding="utf-8",
            )
            (root / "tests" / "test_x.py").write_text(
                'open("test.log", "w").write("x")\n',
                encoding="utf-8",
            )
            (root / "docs" / "example.py").write_text(
                'open("doc.log", "w").write("x")\n',
                encoding="utf-8",
            )

            subprocess.run(
                ["git", "init", "-q"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                [
                    "git",
                    "add",
                    "server_core/state.py",
                    "tools/helper.py",
                    "tests/test_x.py",
                    "docs/example.py",
                ],
                cwd=root,
                check=True,
            )

            result = scan_repository(root)

        self.assertEqual(
            result["production_python_files"],
            1,
        )
        self.assertEqual(len(result["writer_sites"]), 1)
        self.assertEqual(result["violations"], [])

    def test_unresolved_writer_is_inventory_not_static_violation(self):
        writers, _ = scan_python_source(
            """
def save(target, value):
    target.write_text(value)
""",
            "module.py",
        )
        result = {
            "production_python_files": 1,
            "writer_sites": writers,
            "subprocess_sites": [],
            "violations": [],
            "unresolved_writers": writers,
        }

        rendered = "\n".join(render_summary(result))

        self.assertIn(
            "unresolved-writer-sites: 1",
            rendered,
        )
        self.assertIn(
            "PATH-001D.1 static gate: PASS",
            rendered,
        )

    def test_summary_is_value_free_and_gate_passes(self):
        writers, _ = scan_python_source(
            """
def save(paths, secret_value):
    paths.security_state_file.write_text(secret_value)
""",
            "module.py",
        )
        result = {
            "production_python_files": 1,
            "writer_sites": writers,
            "subprocess_sites": [],
            "violations": [],
            "unresolved_writers": [],
        }

        rendered = "\n".join(render_summary(result))

        self.assertIn("PATH-001D.1 static gate: PASS", rendered)
        self.assertNotIn("secret_value", rendered)


if __name__ == "__main__":
    unittest.main()
