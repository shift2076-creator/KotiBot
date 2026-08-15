import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.sec00645_rotate_service_credentials import (
    GROUPS,
    RotationError,
    activate,
    preflight,
    rollback,
    verify_active,
)


def _firebase(key_id: str, private_key: str) -> bytes:
    return (json.dumps({
        "type": "service_account",
        "project_id": "project-for-test",
        "private_key_id": key_id,
        "private_key": (
            "-----BEGIN PRIVATE KEY-----\n"
            f"{private_key}\n"
            "-----END PRIVATE KEY-----\n"
        ),
        "client_email": "fixture@example.test",
        "token_uri": "https://oauth2.example.test/token",
    }) + "\n").encode("utf-8")


class CredentialRotationFixture:
    def __init__(self, root: Path):
        self.root = root
        self.current = root / "current"
        self.candidates = root / "candidates"
        self.state = root / "state"
        self.uid = os.getuid()
        for directory in (self.current, self.candidates, self.state):
            directory.mkdir(mode=0o700)
            directory.chmod(0o700)

    def candidate_directory(self, group: str) -> Path:
        directory = self.candidates / group
        directory.mkdir(mode=0o700)
        directory.chmod(0o700)
        return directory

    def write(self, directory: Path, name: str, value: bytes) -> None:
        path = directory / name
        path.write_bytes(value)
        path.chmod(0o600)

    def write_tapo_account(self) -> tuple[dict[str, bytes], dict[str, bytes]]:
        old = {
            "tapo-username": b"account@example.test\n",
            "tapo-password": b"old-account-password\n",
        }
        new = {
            "tapo-username": b"account@example.test\n",
            "tapo-password": b"new-account-password\n",
        }
        candidate = self.candidate_directory("tapo-account")
        for name, value in old.items():
            self.write(self.current, name, value)
        for name, value in new.items():
            self.write(candidate, name, value)
        return old, new

    def write_tapo_camera(self) -> tuple[dict[str, bytes], dict[str, bytes]]:
        old = {
            "tapo-camera-username": b"camera-user\n",
            "tapo-camera-password": b"old-camera-password\n",
        }
        new = {
            "tapo-camera-username": b"camera-user\n",
            "tapo-camera-password": b"new-camera-password\n",
        }
        candidate = self.candidate_directory("tapo-camera")
        for name, value in old.items():
            self.write(self.current, name, value)
        for name, value in new.items():
            self.write(candidate, name, value)
        return old, new

    def write_firebase(self) -> tuple[bytes, bytes]:
        old = _firebase("old-key-id", "old-private-key")
        new = _firebase("new-key-id", "new-private-key")
        candidate = self.candidate_directory("firebase")
        self.write(self.current, "firebase-service-account.json", old)
        self.write(candidate, "firebase-service-account.json", new)
        return old, new


class Sec00645ServiceCredentialRotationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = CredentialRotationFixture(Path(self.temporary.name))

    def tearDown(self):
        self.temporary.cleanup()

    def test_shared_tapo_account_activation_and_rollback_are_isolated(self):
        old, new = self.fixture.write_tapo_account()
        group = GROUPS["tapo-account"]
        state = self.fixture.state / "tapo-account"
        candidate = self.fixture.candidates / "tapo-account"

        activate(
            group,
            self.fixture.current,
            candidate,
            state,
            expected_uid=self.fixture.uid,
        )
        verify_active(
            group,
            self.fixture.current,
            candidate,
            state,
            expected_uid=self.fixture.uid,
        )

        for name, value in new.items():
            self.assertEqual((self.fixture.current / name).read_bytes(), value)
            self.assertEqual(
                (state / "previous" / name).read_bytes(),
                old[name],
            )
            self.assertEqual(
                (self.fixture.current / name).stat().st_mode & 0o777,
                0o600,
            )

        self.assertNotIn("tapo-camera-password", old)
        self.assertFalse((self.fixture.current / "tapo-camera-password").exists())

    def test_local_camera_account_rotates_as_a_separate_scope(self):
        old, new = self.fixture.write_tapo_camera()
        group = GROUPS["tapo-camera"]
        state = self.fixture.state / "tapo-camera"
        candidate = self.fixture.candidates / "tapo-camera"

        activate(
            group,
            self.fixture.current,
            candidate,
            state,
            expected_uid=self.fixture.uid,
        )
        verify_active(
            group,
            self.fixture.current,
            candidate,
            state,
            expected_uid=self.fixture.uid,
        )

        for name, value in new.items():
            self.assertEqual((self.fixture.current / name).read_bytes(), value)
            self.assertEqual((state / "previous" / name).read_bytes(), old[name])

        self.assertFalse((self.fixture.current / "tapo-password").exists())

    def test_activation_creates_a_missing_private_state_root(self):
        self.fixture.write_firebase()
        self.fixture.state.rmdir()
        state = self.fixture.state / "firebase"

        activate(
            GROUPS["firebase"],
            self.fixture.current,
            self.fixture.candidates / "firebase",
            state,
            expected_uid=self.fixture.uid,
        )

        self.assertTrue(state.is_dir())
        self.assertEqual(self.fixture.state.stat().st_mode & 0o777, 0o700)

    def test_tapo_account_requires_only_shared_password_to_change(self):
        _, new = self.fixture.write_tapo_account()
        candidate = self.fixture.candidates / "tapo-account"
        self.fixture.write(
            candidate,
            "tapo-password",
            b"old-account-password\n",
        )

        with self.assertRaisesRegex(
            RotationError,
            "tapo-password",
        ):
            preflight(
                GROUPS["tapo-account"],
                self.fixture.current,
                candidate,
                self.fixture.state / "tapo-account",
                expected_uid=self.fixture.uid,
            )

        self.assertEqual(
            (candidate / "tapo-username").read_bytes(),
            new["tapo-username"],
        )

    def test_firebase_requires_new_key_id_and_key_material(self):
        old, _ = self.fixture.write_firebase()
        candidate = self.fixture.candidates / "firebase"
        self.fixture.write(
            candidate,
            "firebase-service-account.json",
            old,
        )

        with self.assertRaisesRegex(RotationError, "unchanged"):
            preflight(
                GROUPS["firebase"],
                self.fixture.current,
                candidate,
                self.fixture.state / "firebase",
                expected_uid=self.fixture.uid,
            )

    def test_rejects_symlinked_candidate(self):
        self.fixture.write_tapo_account()
        candidate = self.fixture.candidates / "tapo-account"
        linked = candidate / "tapo-password"
        linked.unlink()
        linked.symlink_to(candidate / "tapo-username")

        with self.assertRaisesRegex(RotationError, "symbolic link"):
            preflight(
                GROUPS["tapo-account"],
                self.fixture.current,
                candidate,
                self.fixture.state / "tapo-account",
                expected_uid=self.fixture.uid,
            )

    def test_rejects_group_readable_candidate(self):
        self.fixture.write_tapo_account()
        candidate = self.fixture.candidates / "tapo-account"
        path = candidate / "tapo-password"
        path.chmod(0o640)

        with self.assertRaisesRegex(RotationError, "not private"):
            preflight(
                GROUPS["tapo-account"],
                self.fixture.current,
                candidate,
                self.fixture.state / "tapo-account",
                expected_uid=self.fixture.uid,
            )

    def test_rejects_multiline_text_candidate(self):
        self.fixture.write_tapo_account()
        candidate = self.fixture.candidates / "tapo-account"
        self.fixture.write(
            candidate,
            "tapo-password",
            b"new-account-password\nsecond-line\n",
        )

        with self.assertRaisesRegex(RotationError, "one text line"):
            preflight(
                GROUPS["tapo-account"],
                self.fixture.current,
                candidate,
                self.fixture.state / "tapo-account",
                expected_uid=self.fixture.uid,
            )

    def test_activation_failure_restores_every_previous_file(self):
        old, _ = self.fixture.write_tapo_account()
        group = GROUPS["tapo-account"]
        state = self.fixture.state / "tapo-account"
        candidate = self.fixture.candidates / "tapo-account"
        from tools import sec00645_rotate_service_credentials as module

        original_atomic_write = module._atomic_write
        injected = {"done": False}

        def failing_write(path, data, *, owner_uid):
            if (
                path.parent == self.fixture.current
                and path.name == "tapo-password"
                and not injected["done"]
            ):
                injected["done"] = True
                raise OSError("injected write failure")
            return original_atomic_write(path, data, owner_uid=owner_uid)

        with mock.patch.object(module, "_atomic_write", failing_write):
            with self.assertRaisesRegex(RotationError, "restored"):
                activate(
                    group,
                    self.fixture.current,
                    candidate,
                    state,
                    expected_uid=self.fixture.uid,
                )

        for name, value in old.items():
            self.assertEqual((self.fixture.current / name).read_bytes(), value)

    def test_explicit_rollback_restores_previous_bundle(self):
        old, _ = self.fixture.write_tapo_account()
        group = GROUPS["tapo-account"]
        state = self.fixture.state / "tapo-account"
        candidate = self.fixture.candidates / "tapo-account"
        activate(
            group,
            self.fixture.current,
            candidate,
            state,
            expected_uid=self.fixture.uid,
        )

        rollback(
            group,
            self.fixture.current,
            state,
            expected_uid=self.fixture.uid,
        )

        for name, value in old.items():
            self.assertEqual((self.fixture.current / name).read_bytes(), value)
        manifest = json.loads((state / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "rolled-back")

    def test_errors_and_success_output_do_not_disclose_values(self):
        self.fixture.write_tapo_account()
        candidate = self.fixture.candidates / "tapo-account"
        from tools import sec00645_rotate_service_credentials as module

        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            module._print_result("preflight", GROUPS["tapo-account"])
        rendered = output.getvalue()

        for private_value in (
            "account@example.test",
            "old-account-password",
            "new-account-password",
            "old-camera-password",
            "new-camera-password",
        ):
            self.assertNotIn(private_value, rendered)

        self.assertTrue(candidate.exists())


if __name__ == "__main__":
    unittest.main()
