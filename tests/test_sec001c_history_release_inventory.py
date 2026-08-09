import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SCANNER_PATH = (
    ROOT
    / "tools"
    / "sec001c_history_release_inventory.py"
)
SPEC = importlib.util.spec_from_file_location(
    "sec001c_inventory",
    SCANNER_PATH,
)
SEC001C = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = SEC001C
SPEC.loader.exec_module(SEC001C)


class SEC001CHistoryReleaseInventoryTests(
    unittest.TestCase
):
    def git(
        self,
        repository: Path,
        *arguments: str,
    ) -> str:
        result = subprocess.run(
            (
                "git",
                "-C",
                os.fspath(repository),
                *arguments,
            ),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return result.stdout.strip()

    def make_repository(
        self,
        root: Path,
    ) -> tuple[Path, str, str]:
        repository = root / "repository"
        repository.mkdir()

        self.git(
            repository,
            "init",
            "--quiet",
        )
        self.git(
            repository,
            "config",
            "user.name",
            "SEC001C Test",
        )
        self.git(
            repository,
            "config",
            "user.email",
            "sec001c@example.invalid",
        )

        (
            repository
            / "README.md"
        ).write_text(
            "fixture\n",
            encoding="utf-8",
        )

        self.git(
            repository,
            "add",
            "README.md",
        )
        self.git(
            repository,
            "commit",
            "--quiet",
            "-m",
            "fixture root",
        )
        first_commit = self.git(
            repository,
            "rev-parse",
            "HEAD",
        )

        secret_file = repository / ".env.saved"
        secret_file.write_text(
            (
                "TAPO_PASSWORD="
                "history-value-must-not-leak\n"
                "NORMAL_SETTING="
                "ordinary-value-must-not-leak\n"
            ),
            encoding="utf-8",
        )

        self.git(
            repository,
            "add",
            ".env.saved",
        )
        self.git(
            repository,
            "commit",
            "--quiet",
            "-m",
            "add fixture",
        )
        second_commit = self.git(
            repository,
            "rev-parse",
            "HEAD",
        )

        self.git(
            repository,
            "tag",
            "-a",
            "v-fixture",
            "-m",
            "PASSWORD=tag-value-must-not-leak",
        )

        secret_file.unlink()
        self.git(
            repository,
            "add",
            "-u",
        )
        self.git(
            repository,
            "commit",
            "--quiet",
            "-m",
            "remove fixture",
        )

        return (
            repository,
            first_commit,
            second_commit,
        )

    def test_report_keeps_names_and_discards_values(
        self,
    ):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (
                repository,
                _first_commit,
                suspect_commit,
            ) = self.make_repository(root)

            archive = (
                repository
                / "temp"
                / "KotiBot-release.zip"
            )
            archive.parent.mkdir()

            with zipfile.ZipFile(
                archive,
                "w",
            ) as handle:
                handle.writestr(
                    (
                        "subsystems/notifications/"
                        "firebase-service-account.json"
                    ),
                    (
                        '{"private_key":'
                        '"archive-value-must-not-leak",'
                        '"project_id":"fixture"}'
                    ),
                )

            (
                head,
                ref_count,
                commit_count,
                history_findings,
                tags,
                tag_findings,
                git_issues,
            ) = SEC001C.scan_git(
                repository,
                SEC001C.DEFAULT_MAX_TEXT_BYTES,
            )

            (
                archives,
                archive_findings,
                archive_issues,
            ) = SEC001C.scan_archives(
                repository,
                (),
                SEC001C.DEFAULT_MAX_TEXT_BYTES,
                SEC001C.DEFAULT_MAX_ARCHIVE_BYTES,
                SEC001C.DEFAULT_MAX_ARCHIVE_MEMBERS,
            )

            report = SEC001C.render_report(
                SEC001C.ScanResult(
                    head_commit=head,
                    ref_count=ref_count,
                    commit_count=commit_count,
                    history_findings=history_findings,
                    tags=tags,
                    tag_findings=tag_findings,
                    archives=archives,
                    archive_findings=archive_findings,
                    issues=[
                        *git_issues,
                        *archive_issues,
                    ],
                )
            )

            self.assertIn(
                suspect_commit,
                report,
            )
            self.assertIn(
                ".env.saved",
                report,
            )
            self.assertIn(
                "TAPO_PASSWORD",
                report,
            )
            self.assertIn(
                "v-fixture",
                report,
            )
            self.assertIn(
                "PASSWORD",
                report,
            )
            self.assertIn(
                "KotiBot-release.zip",
                report,
            )
            self.assertIn(
                "firebase-service-account.json",
                report,
            )
            self.assertIn(
                "private_key",
                report,
            )
            self.assertNotIn(
                str(repository.parent),
                report,
            )
            self.assertNotIn(
                "history-value-must-not-leak",
                report,
            )
            self.assertNotIn(
                "ordinary-value-must-not-leak",
                report,
            )
            self.assertNotIn(
                "tag-value-must-not-leak",
                report,
            )
            self.assertNotIn(
                "archive-value-must-not-leak",
                report,
            )

    def test_private_report_is_atomic_and_private(
        self,
    ):
        if os.name == "nt":
            self.skipTest(
                "POSIX permission assertion"
            )

        with TemporaryDirectory() as temporary_directory:
            output = (
                Path(temporary_directory)
                / "audit"
                / "report.md"
            )

            SEC001C.write_private_report(
                output,
                "names only\n",
            )

            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "names only\n",
            )
            self.assertEqual(
                stat.S_IMODE(output.stat().st_mode),
                0o600,
            )
            self.assertEqual(
                stat.S_IMODE(
                    output.parent.stat().st_mode
                ),
                0o700,
            )
            self.assertFalse(
                output.with_suffix(
                    ".md.tmp"
                ).exists()
            )

    def test_unsupported_archive_is_inventoried_for_follow_up(
        self,
    ):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (
                repository,
                _first_commit,
                _second_commit,
            ) = self.make_repository(root)

            unsupported = repository / "release.7z"
            unsupported.write_bytes(b"not opened")

            (
                records,
                findings,
                issues,
            ) = SEC001C.scan_archives(
                repository,
                (),
                SEC001C.DEFAULT_MAX_TEXT_BYTES,
                SEC001C.DEFAULT_MAX_ARCHIVE_BYTES,
                SEC001C.DEFAULT_MAX_ARCHIVE_MEMBERS,
            )

            self.assertEqual(
                len(records),
                1,
            )
            self.assertEqual(
                records[0].status,
                "unsupported",
            )
            self.assertEqual(
                findings,
                [],
            )
            self.assertEqual(
                issues[0].status,
                "unsupported format",
            )

    def test_archive_symlinks_are_inventoried_but_not_followed(
        self,
    ):
        if os.name == "nt":
            self.skipTest(
                "POSIX symlink assertion"
            )

        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (
                repository,
                _first_commit,
                _second_commit,
            ) = self.make_repository(root)

            target = root / "external.zip"

            with zipfile.ZipFile(
                target,
                "w",
            ) as handle:
                handle.writestr(
                    "secret.json",
                    '{"password":"must-not-be-read"}',
                )

            (
                repository
                / "release.zip"
            ).symlink_to(target)

            (
                records,
                findings,
                issues,
            ) = SEC001C.scan_archives(
                repository,
                (),
                SEC001C.DEFAULT_MAX_TEXT_BYTES,
                SEC001C.DEFAULT_MAX_ARCHIVE_BYTES,
                SEC001C.DEFAULT_MAX_ARCHIVE_MEMBERS,
            )

            self.assertEqual(
                records[0].status,
                "symlink not followed",
            )
            self.assertEqual(
                findings,
                [],
            )
            self.assertEqual(
                issues[0].status,
                "symlink not followed",
            )


if __name__ == "__main__":
    unittest.main()