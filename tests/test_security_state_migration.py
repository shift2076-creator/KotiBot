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

    def test_server_wires_security_state_to_runtime_path(self):
        source = (SOURCE_ROOT / "kotibot_server.py").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "SECURITY_STATE_FILE = RUNTIME_PATHS.security_state_file",
            source,
        )
        self.assertIn(
            "LEGACY_SECURITY_STATE_FILE = SECURITY_DIR / "
            "'security_state.json'",
            source,
        )
        self.assertIn(
            "SECURITY_STATE_FILE.parent,\n"
            "    legacy_state_file=LEGACY_SECURITY_STATE_FILE,",
            source,
        )

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
    def test_valid_legacy_state_migrates_once_with_private_lkg(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy_file = root / "legacy" / "security_state.json"
            state_dir = root / "protected" / "security"
            expected = {"migration_marker": {"preserved": True}}
            write_json_atomic_sync(legacy_file, expected)

            security = KotiBotSecurity(SecurityConfig(
                base_dir=state_dir,
                legacy_state_path=legacy_file,
                allowed_origins=(
                    ("https", "kotibot.example", 443),
                ),
            ))

            state_file = security.config.state_file
            backup_file = json_backup_path(state_file)
            self.assertEqual(
                read_json(state_file)["migration_marker"],
                expected["migration_marker"],
            )
            self.assertEqual(
                read_json(backup_file)["migration_marker"],
                expected["migration_marker"],
            )

            if os.name != "nt":
                self.assertEqual(
                    stat.S_IMODE(state_file.stat().st_mode),
                    0o600,
                )
                self.assertEqual(
                    stat.S_IMODE(backup_file.stat().st_mode),
                    0o600,
                )

            changed_legacy = {"migration_marker": {"preserved": False}}
            write_json_atomic_sync(legacy_file, changed_legacy)
            second = KotiBotSecurity(SecurityConfig(
                base_dir=state_dir,
                legacy_state_path=legacy_file,
                allowed_origins=(
                    ("https", "kotibot.example", 443),
                ),
            ))
            self.assertTrue(
                second.state["migration_marker"]["preserved"]
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
        KotiBotSecurity is None,
        "Flask is not installed in this development environment",
    )
    def test_legacy_lkg_blocks_empty_migration(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy_file = root / "legacy" / "security_state.json"
            write_json_atomic_sync(legacy_file, {"version": 1})
            legacy_file.unlink()

            with self.assertRaisesRegex(
                RuntimeError,
                "Legacy security state primary is missing",
            ):
                KotiBotSecurity(SecurityConfig(
                    base_dir=root / "protected" / "security",
                    legacy_state_path=legacy_file,
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
