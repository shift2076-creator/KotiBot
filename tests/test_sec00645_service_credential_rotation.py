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
    stage_candidate,
    verify_active,
    verify_runtime_snapshot,
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

    def test_camera_candidate_staging_copies_username_and_replaces_password(self):
        old = {
            "tapo-camera-username": b"camera-user\n",
            "tapo-camera-password": b"old-camera-password\n",
        }
        for name, value in old.items():
            self.fixture.write(self.fixture.current, name, value)
        candidate = self.fixture.candidates / "tapo-camera"

        stage_candidate(
            GROUPS["tapo-camera"],
            self.fixture.current,
            candidate,
            self.fixture.state / "tapo-camera",
            {"tapo-camera-password": b"new-camera-password\n"},
            expected_uid=self.fixture.uid,
        )

        self.assertEqual(
            (candidate / "tapo-camera-username").read_bytes(),
            old["tapo-camera-username"],
        )
        self.assertEqual(
            (candidate / "tapo-camera-password").read_bytes(),
            b"new-camera-password\n",
        )
        for name in GROUPS["tapo-camera"].credential_names:
            self.assertEqual((candidate / name).stat().st_mode & 0o777, 0o600)

    def test_staging_rejects_textually_unchanged_password(self):
        self.fixture.write(
            self.fixture.current,
            "tapo-camera-username",
            b"camera-user",
        )
        self.fixture.write(
            self.fixture.current,
            "tapo-camera-password",
            b"same-password",
        )

        with self.assertRaisesRegex(RotationError, "unchanged"):
            stage_candidate(
                GROUPS["tapo-camera"],
                self.fixture.current,
                self.fixture.candidates / "tapo-camera",
                self.fixture.state / "tapo-camera",
                {"tapo-camera-password": b"same-password\n"},
                expected_uid=self.fixture.uid,
            )

    def test_firebase_candidate_staging_requires_rotated_key_material(self):
        old = _firebase("old-key-id", "old-private-key")
        new = _firebase("new-key-id", "new-private-key")
        self.fixture.write(
            self.fixture.current,
            "firebase-service-account.json",
            old,
        )
        candidate = self.fixture.candidates / "firebase"

        stage_candidate(
            GROUPS["firebase"],
            self.fixture.current,
            candidate,
            self.fixture.state / "firebase",
            {"firebase-service-account.json": new},
            expected_uid=self.fixture.uid,
        )

        self.assertEqual(
            (candidate / "firebase-service-account.json").read_bytes(),
            new,
        )
        self.assertEqual(
            (candidate / "firebase-service-account.json").stat().st_mode & 0o777,
            0o600,
        )

    def test_firebase_candidate_source_must_be_private_and_not_symlinked(self):
        from tools import sec00645_rotate_service_credentials as module

        source = self.fixture.root / "new-service-account.json"
        source.write_bytes(_firebase("new-key-id", "new-private-key"))
        source.chmod(0o640)
        with self.assertRaisesRegex(RotationError, "not private"):
            module._read_private_candidate_source(
                source,
                "Firebase candidate source",
                max_bytes=module.MAX_JSON_BYTES,
            )

        source.chmod(0o600)
        self.assertEqual(
            module._read_private_candidate_source(
                source,
                "Firebase candidate source",
                max_bytes=module.MAX_JSON_BYTES,
            ),
            source.read_bytes(),
        )

        linked = self.fixture.root / "linked-service-account.json"
        linked.symlink_to(source)
        with self.assertRaisesRegex(RotationError, "symbolic link"):
            module._read_private_candidate_source(
                linked,
                "Firebase candidate source",
                max_bytes=module.MAX_JSON_BYTES,
            )

    def test_text_staging_requires_matching_hidden_confirmation(self):
        from tools import sec00645_rotate_service_credentials as module

        with mock.patch.object(
            module.getpass,
            "getpass",
            side_effect=("new-password", "different-password"),
        ):
            with self.assertRaisesRegex(RotationError, "does not match"):
                module._prompt_text_replacements(GROUPS["tapo-camera"])

    def test_staging_refuses_existing_candidate_or_rotation_state(self):
        old = {
            "tapo-camera-username": b"camera-user\n",
            "tapo-camera-password": b"old-camera-password\n",
        }
        for name, value in old.items():
            self.fixture.write(self.fixture.current, name, value)
        candidate = self.fixture.candidate_directory("tapo-camera")

        with self.assertRaisesRegex(RotationError, "candidate already exists"):
            stage_candidate(
                GROUPS["tapo-camera"],
                self.fixture.current,
                candidate,
                self.fixture.state / "tapo-camera",
                {"tapo-camera-password": b"new-camera-password\n"},
                expected_uid=self.fixture.uid,
            )

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

    def test_runtime_verification_checks_the_active_systemd_snapshot(self):
        from tools import sec00645_rotate_service_credentials as module

        self.fixture.write_firebase()
        group = GROUPS["firebase"]
        candidate = self.fixture.candidates / "firebase"
        state = self.fixture.state / "firebase"
        activate(
            group,
            self.fixture.current,
            candidate,
            state,
            expected_uid=self.fixture.uid,
        )
        snapshot = mock.Mock(
            runtime_credential_directory=self.fixture.root / "runtime",
            process_user_id=1234,
            process_group_id=1235,
        )

        with (
            mock.patch.object(
                module,
                "inspect_active_service",
                return_value=snapshot,
            ) as inspect_service,
            mock.patch.object(
                module,
                "verify_service_credential_copies",
                return_value=({}, {}),
            ) as verify_copies,
        ):
            verify_runtime_snapshot(
                group,
                self.fixture.current,
                candidate,
                state,
                "kotibot",
                expected_uid=self.fixture.uid,
                expected_source_owner=(self.fixture.uid, os.getgid()),
            )

        inspect_service.assert_called_once_with("kotibot")
        verify_copies.assert_called_once_with(
            self.fixture.current,
            snapshot.runtime_credential_directory,
            expected_source_owner=(self.fixture.uid, os.getgid()),
            expected_runtime_owners=frozenset({
                (0, 0),
                (snapshot.process_user_id, snapshot.process_group_id),
            }),
        )

    def test_runtime_verification_fails_closed_on_service_mismatch(self):
        from tools import sec00645_rotate_service_credentials as module

        self.fixture.write_firebase()
        group = GROUPS["firebase"]
        candidate = self.fixture.candidates / "firebase"
        state = self.fixture.state / "firebase"
        activate(
            group,
            self.fixture.current,
            candidate,
            state,
            expected_uid=self.fixture.uid,
        )
        snapshot = mock.Mock(
            runtime_credential_directory=self.fixture.root / "runtime",
            process_user_id=1234,
            process_group_id=1235,
        )

        with (
            mock.patch.object(
                module,
                "inspect_active_service",
                return_value=snapshot,
            ),
            mock.patch.object(
                module,
                "verify_service_credential_copies",
                side_effect=RuntimeError("runtime copy mismatch"),
            ),
            self.assertRaisesRegex(
                RotationError,
                "Live service credential verification failed",
            ),
        ):
            verify_runtime_snapshot(
                group,
                self.fixture.current,
                candidate,
                state,
                "kotibot",
                expected_uid=self.fixture.uid,
                expected_source_owner=(self.fixture.uid, os.getgid()),
            )

    def test_errors_and_success_output_do_not_disclose_values(self):
        self.fixture.write_tapo_account()
        candidate = self.fixture.candidates / "tapo-account"
        from tools import sec00645_rotate_service_credentials as module

        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            module._print_result("stage", GROUPS["tapo-account"])
            module._print_result("preflight", GROUPS["tapo-account"])
            module._print_result("runtime-verify", GROUPS["firebase"])
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
