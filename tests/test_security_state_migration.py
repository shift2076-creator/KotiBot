import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from server_core.io import (
    json_backup_path,
    read_json,
    write_json_atomic_sync,
)
from server_core.paths import (
    build_runtime_paths,
    prepare_runtime_directories,
)

try:
    from subsystems.security.kotibot_security import (
        KotiBotSecurity,
        SecurityConfig,
    )
except ModuleNotFoundError as exc:
    if exc.name != "flask":
        raise

    KotiBotSecurity = None
    SecurityConfig = None


SOURCE_ROOT = Path(__file__).resolve().parents[1]


class SecurityStateMigrationTests(unittest.TestCase):
    def test_security_state_is_in_private_runtime_root(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            data_root = root / "app-data"
            source_root.mkdir()

            with patch.dict(
                os.environ,
                {"KOTIBOT_DATA_DIR": str(data_root)},
                clear=True,
            ):
                paths = build_runtime_paths(source_root)

            self.assertEqual(
                paths.security_state_file,
                data_root
                / "protected"
                / "security"
                / "security_state.json",
            )
            self.assertNotIn(
                source_root.resolve(),
                paths.security_state_file.resolve().parents,
            )

    def test_prepare_creates_private_security_state_directory(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            data_root = root / "app-data"
            source_root.mkdir()

            with patch.dict(
                os.environ,
                {"KOTIBOT_DATA_DIR": str(data_root)},
                clear=True,
            ):
                paths = build_runtime_paths(source_root)
                prepare_runtime_directories(paths)

            self.assertTrue(paths.security_state_dir.is_dir())

            if os.name != "nt":
                self.assertEqual(
                    stat.S_IMODE(
                        paths.security_state_dir.stat().st_mode
                    ),
                    0o700,
                )

    def test_server_wires_only_the_protected_security_state(self):
        source = (SOURCE_ROOT / "kotibot_server.py").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "SECURITY_STATE_FILE = RUNTIME_PATHS.security_state_file",
            source,
        )
        self.assertIn(
            "SECURITY = make_security(\n"
            "    SECURITY_STATE_FILE.parent,\n"
            "    audit_file=RUNTIME_PATHS.security_audit_file,",
            source,
        )
        self.assertNotIn("LEGACY_SECURITY_STATE_FILE", source)
        self.assertNotIn("legacy_state_file=", source)

    def test_security_cli_uses_runtime_resolver(self):
        source = (
            SOURCE_ROOT
            / "subsystems"
            / "security"
            / "kotibot_security.py"
        ).read_text(encoding="utf-8")

        cli_source = source.split("def _cli() -> int:", 1)[1]
        self.assertIn("build_runtime_paths(source_root)", cli_source)
        self.assertIn("runtime_paths.security_state_dir", cli_source)
        self.assertNotIn(
            "make_security(Path(__file__).parent)",
            cli_source,
        )

    @unittest.skipIf(
        KotiBotSecurity is None,
        "Flask is not installed in this development environment",
    )
    def test_destination_lkg_blocks_empty_reinitialization(self):
        with TemporaryDirectory() as temp_dir:
            state_dir = Path(temp_dir) / "protected" / "security"
            state_file = state_dir / "security_state.json"
            write_json_atomic_sync(state_file, {"version": 1})
            state_file.unlink()

            with self.assertRaisesRegex(
                RuntimeError,
                "primary is missing",
            ):
                KotiBotSecurity(SecurityConfig(
                    base_dir=state_dir,
                    allowed_origins=(
                        ("https", "kotibot.example", 443),
                    ),
                ))

    @unittest.skipIf(
        os.name == "nt" or KotiBotSecurity is None,
        "Symbolic-link migration test requires POSIX and Flask",
    )
    def test_symbolic_link_destination_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_dir = root / "protected" / "security"
            state_dir.mkdir(parents=True)
            target = root / "outside.json"
            write_json_atomic_sync(target, {"version": 1})
            state_file = state_dir / "security_state.json"
            state_file.symlink_to(target)

            with self.assertRaisesRegex(
                RuntimeError,
                "must not be a symbolic link",
            ):
                KotiBotSecurity(SecurityConfig(
                    base_dir=state_dir,
                    allowed_origins=(
                        ("https", "kotibot.example", 443),
                    ),
                ))


if __name__ == "__main__":
    unittest.main()
