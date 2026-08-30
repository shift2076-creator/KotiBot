from __future__ import annotations

from dataclasses import fields
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from server_core.paths import (
    RuntimePaths,
    build_runtime_paths,
)
from tools.path001d3_verify_source_boundary import (
    DEVELOPER_CONTENT_DIRS,
    evaluate_destinations,
    run,
)


class Path001D3SourceBoundaryTests(unittest.TestCase):
    def test_destination_inventory_covers_roots_and_path_properties(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = RuntimePaths(
                source_root=root / "source",
                data_root=root / "data",
                cache_root=root / "cache",
                runtime_root=root / "runtime",
                temporary_root=root / "temporary",
                package_root=root / "packages",
                media_root=root / "media",
            )

            expected = {
                field.name
                for field in fields(RuntimePaths)
                if field.name != "source_root"
            }
            expected.update(
                name
                for name, descriptor in vars(RuntimePaths).items()
                if isinstance(descriptor, property)
            )

            self.assertEqual(
                set(paths.resolved_runtime_destinations()),
                expected,
            )

    def test_every_declared_destination_is_absolute_and_external(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            data_root = root / "data"
            source_root.mkdir()

            with patch.dict(
                os.environ,
                {"KOTIBOT_DATA_DIR": str(data_root)},
                clear=True,
            ):
                paths = build_runtime_paths(source_root)

            result = evaluate_destinations(
                source_root,
                paths.resolved_runtime_destinations(),
            )

            self.assertGreater(result["resolved"], 0)
            self.assertEqual(result["non_absolute"], 0)
            self.assertEqual(result["inside_source"], 0)
            self.assertEqual(
                result["developer_content_targets"],
                0,
            )

    def test_each_configurable_root_is_rejected_inside_source(self):
        environment_names = (
            "KOTIBOT_DATA_DIR",
            "KOTIBOT_CACHE_DIR",
            "KOTIBOT_RUNTIME_DIR",
            "KOTIBOT_TEMP_DIR",
            "KOTIBOT_PACKAGE_DIR",
            "KOTIBOT_MEDIA_DIR",
            "KOTIBOT_TAPO_RECORDING_DIR",
        )

        for environment_name in environment_names:
            with self.subTest(environment_name=environment_name):
                with TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    source_root = root / "source"
                    source_root.mkdir()
                    environment = {
                        "KOTIBOT_DATA_DIR": str(root / "data"),
                        "KOTIBOT_CACHE_DIR": str(root / "cache"),
                        "KOTIBOT_RUNTIME_DIR": str(root / "runtime"),
                        "KOTIBOT_TEMP_DIR": str(root / "temporary"),
                        "KOTIBOT_PACKAGE_DIR": str(root / "packages"),
                    }

                    if environment_name == "KOTIBOT_TAPO_RECORDING_DIR":
                        environment.pop("KOTIBOT_MEDIA_DIR", None)

                    environment[environment_name] = str(
                        source_root / "runtime"
                    )

                    with patch.dict(
                        os.environ,
                        environment,
                        clear=True,
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError,
                            "outside the source tree",
                        ):
                            build_runtime_paths(source_root)

    def test_developer_content_directories_are_explicitly_rejected(self):
        for directory_name in DEVELOPER_CONTENT_DIRS:
            with self.subTest(directory_name=directory_name):
                with TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    source_root = root / "source"
                    source_root.mkdir()

                    with patch.dict(
                        os.environ,
                        {
                            "KOTIBOT_DATA_DIR": str(
                                source_root / directory_name
                            )
                        },
                        clear=True,
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError,
                            "outside the source tree",
                        ):
                            build_runtime_paths(source_root)

    @unittest.skipIf(
        os.name == "nt",
        "symlink containment semantics differ on Windows",
    )
    def test_symlink_alias_into_source_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            source_root.mkdir()
            alias = root / "runtime-alias"
            alias.symlink_to(
                source_root / "runtime",
                target_is_directory=True,
            )

            with patch.dict(
                os.environ,
                {"KOTIBOT_DATA_DIR": str(alias)},
                clear=True,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "outside the source tree",
                ):
                    build_runtime_paths(source_root)

    def test_new_path_property_cannot_bypass_validation(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            source_root.mkdir()
            paths = RuntimePaths(
                source_root=source_root,
                data_root=root / "data",
            )

            with patch.object(
                RuntimePaths,
                "future_runtime_file",
                property(
                    lambda _self:
                    source_root / "future-runtime.json"
                ),
                create=True,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "outside the source tree",
                ):
                    paths.validate()

    def test_relative_destination_is_rejected(self):
        paths = RuntimePaths(
            source_root=Path("/absolute/source"),
            data_root=Path("relative-data"),
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "must be absolute",
        ):
            paths.validate()

    def test_verifier_stops_before_path_resolution_on_head_mismatch(self):
        args = SimpleNamespace(
            root=Path("/untrusted/source"),
            expected_head="expected",
        )

        with patch(
            "tools.path001d3_verify_source_boundary._git_head",
            return_value="different",
        ), patch(
            "server_core.paths.build_runtime_paths",
            side_effect=AssertionError(
                "path environment must not be read after mismatch"
            ),
        ):
            self.assertEqual(run(args), 2)


if __name__ == "__main__":
    unittest.main()
