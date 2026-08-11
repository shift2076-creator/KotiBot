import io
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from tools.sec004_migrate_service_credentials import (
    FIREBASE_CREDENTIAL_NAME,
    TAPO_CREDENTIALS,
    _running_service_environment,
    main,
    migrate,
)


class ServiceCredentialMigrationTests(unittest.TestCase):
    def _environment(self, marker: str = "source") -> dict[str, str]:
        return {
            environment_name: f"{marker}-{credential_name}"
            for credential_name, environment_name in TAPO_CREDENTIALS
        }

    def _firebase_source(self, root: Path, marker: str = "source") -> Path:
        path = root / "legacy" / FIREBASE_CREDENTIAL_NAME
        path.parent.mkdir(parents=True)
        path.write_text(
            '{"type":"service_account","marker":"'
            + marker
            + '"}',
            encoding="utf-8",
        )

        if os.name != "nt":
            path.chmod(0o600)

        return path

    def test_preflight_is_read_only_and_reports_all_credentials(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            destination = root / "credentials"
            firebase_source = self._firebase_source(root)

            statuses = migrate(
                destination=destination,
                firebase_source=firebase_source,
                copy=False,
                environment=self._environment(),
            )

            self.assertFalse(destination.exists())
            self.assertEqual(
                set(statuses),
                {
                    *(name for name, _ in TAPO_CREDENTIALS),
                    FIREBASE_CREDENTIAL_NAME,
                },
            )
            self.assertEqual(set(statuses.values()), {"ready"})
            self.assertTrue(firebase_source.exists())

    def test_copy_is_atomic_private_and_retains_all_legacy_sources(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            destination = root / "credentials"
            environment = self._environment()
            firebase_source = self._firebase_source(root)
            firebase_payload = firebase_source.read_bytes()

            statuses = migrate(
                destination=destination,
                firebase_source=firebase_source,
                copy=True,
                environment=environment,
            )

            self.assertEqual(set(statuses.values()), {"copied"})

            for credential_name, environment_name in TAPO_CREDENTIALS:
                self.assertEqual(
                    (destination / credential_name).read_text(
                        encoding="utf-8"
                    ),
                    environment[environment_name],
                )

            self.assertEqual(
                (destination / FIREBASE_CREDENTIAL_NAME).read_bytes(),
                firebase_payload,
            )
            self.assertTrue(firebase_source.exists())
            self.assertFalse(list(destination.glob(".*.tmp")))

            if os.name != "nt":
                self.assertEqual(
                    stat.S_IMODE(destination.stat().st_mode),
                    0o700,
                )

                for path in destination.iterdir():
                    self.assertEqual(
                        stat.S_IMODE(path.stat().st_mode),
                        0o600,
                    )

    def test_repeat_copy_is_idempotent(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            destination = root / "credentials"
            environment = self._environment()
            firebase_source = self._firebase_source(root)
            migrate(
                destination=destination,
                firebase_source=firebase_source,
                copy=True,
                environment=environment,
            )

            statuses = migrate(
                destination=destination,
                firebase_source=firebase_source,
                copy=True,
                environment=environment,
            )

            self.assertEqual(
                set(statuses.values()),
                {"already-current"},
            )

    def test_conflict_stops_before_any_missing_destination_is_written(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            destination = root / "credentials"
            destination.mkdir(mode=0o700)
            first_name = TAPO_CREDENTIALS[0][0]
            conflict = destination / first_name
            conflict.write_text("different", encoding="utf-8")

            if os.name != "nt":
                conflict.chmod(0o600)

            with self.assertRaisesRegex(RuntimeError, "conflicts"):
                migrate(
                    destination=destination,
                    firebase_source=self._firebase_source(root),
                    copy=True,
                    environment=self._environment(),
                )

            self.assertEqual(
                sorted(path.name for path in destination.iterdir()),
                [first_name],
            )

    def test_missing_legacy_variable_stops_before_destination_creation(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            destination = root / "credentials"
            environment = self._environment()
            environment.pop(TAPO_CREDENTIALS[-1][1])

            with self.assertRaisesRegex(RuntimeError, "Legacy source is missing"):
                migrate(
                    destination=destination,
                    firebase_source=self._firebase_source(root),
                    copy=True,
                    environment=environment,
                )

            self.assertFalse(destination.exists())

    @unittest.skipIf(os.name == "nt", "Symbolic-link test requires POSIX")
    def test_symbolic_link_destination_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            real = root / "real"
            real.mkdir()
            destination = root / "credentials"
            destination.symlink_to(real, target_is_directory=True)

            with self.assertRaisesRegex(RuntimeError, "symbolic link"):
                migrate(
                    destination=destination,
                    firebase_source=self._firebase_source(root),
                    copy=False,
                    environment=self._environment(),
                )

    def test_running_service_environment_reads_only_required_names(self):
        service_environment = b"".join(
            [
                f"{environment_name}=value-{index}\0".encode("utf-8")
                for index, (_, environment_name) in enumerate(
                    TAPO_CREDENTIALS
                )
            ]
        ) + b"UNRELATED=ignore-me\0"
        completed = Mock(stdout="4321\n")

        with patch(
            "tools.sec004_migrate_service_credentials.subprocess.run",
            return_value=completed,
        ) as run:
            with patch(
                "tools.sec004_migrate_service_credentials.Path.read_bytes",
                return_value=service_environment,
            ):
                environment = _running_service_environment("kotibot")

        self.assertEqual(
            set(environment),
            {name for _, name in TAPO_CREDENTIALS},
        )
        self.assertNotIn("UNRELATED", environment)
        self.assertNotIn("ignore-me", repr(run.call_args))

    def test_cli_output_never_contains_credential_values(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            destination = root / "credentials"
            firebase_source = self._firebase_source(root, "private-marker")
            environment = self._environment("private-marker")
            output = io.StringIO()
            arguments = [
                "sec004_migrate_service_credentials.py",
                "--destination",
                str(destination),
                "--firebase-source",
                str(firebase_source),
            ]

            with patch.dict(os.environ, environment, clear=True):
                with patch("sys.argv", arguments):
                    with patch("sys.stdout", output):
                        result = main()

            self.assertEqual(result, 0)
            self.assertNotIn("private-marker", output.getvalue())
            self.assertIn("preflight passed", output.getvalue())


if __name__ == "__main__":
    unittest.main()
