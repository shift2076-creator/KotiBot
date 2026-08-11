import ast
from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def read_source(relative_path):
    path = REPOSITORY_ROOT / relative_path
    source = path.read_text(encoding="utf-8")
    ast.parse(source, filename=str(path))
    return source


class TapoHlsRuntimePathTests(unittest.TestCase):
    def test_server_threads_resolved_hls_path_to_subsystems(self):
        source = read_source("kotibot_server.py")

        self.assertIn(
            "TAPO_CAMERA_HLS_DIR = "
            "RUNTIME_PATHS.tapo_camera_hls_dir",
            source,
        )
        self.assertIn(
            "'tapo_camera_hls_dir': TAPO_CAMERA_HLS_DIR",
            source,
        )

    def test_subsystem_threads_hls_path_to_tapo_routes(self):
        source = read_source("server_core/subsystems.py")

        self.assertIn(
            "tapo_camera_hls_dir = "
            "Path(ctx['tapo_camera_hls_dir'])",
            source,
        )
        self.assertIn(
            "'tapo_camera_hls_dir': tapo_camera_hls_dir",
            source,
        )

    def test_tapo_control_has_no_source_derived_hls_root(self):
        source = read_source(
            "subsystems/client-tapo/tapo_control.py"
        )

        self.assertNotIn("TAPO_CAMERA_RUNTIME_ROOT", source)
        self.assertNotIn("TAPO_CAMERA_HLS_ROOT", source)
        self.assertIn(
            "def start_tapo_camera_stream(c, *, hls_root):",
            source,
        )
        self.assertIn(
            "def stop_tapo_camera_stream(deviceID, *, hls_root):",
            source,
        )
        self.assertIn(
            "def prune_tapo_camera_streams(*, hls_root):",
            source,
        )
        self.assertEqual(
            source.count("stream_dir = Path(hls_root) / key"),
            2,
        )
        self.assertIn(
            "stop_tapo_camera_stream(key, hls_root=hls_root)",
            source,
        )

    def test_routes_use_explicit_hls_root_and_keep_urls(self):
        source = read_source(
            "subsystems/client-tapo/tapo_routes.py"
        )

        self.assertNotIn("TAPO_CAMERA_HLS_ROOT", source)
        self.assertIn(
            "tapo_camera_hls_dir = "
            "Path(ctx['tapo_camera_hls_dir'])",
            source,
        )
        self.assertIn(
            "hls_url = start_tapo_camera_stream(",
            source,
        )
        self.assertEqual(
            source.count("stop_tapo_camera_stream("),
            3,
        )
        self.assertIn(
            "prune_tapo_camera_streams(",
            source,
        )
        self.assertEqual(
            source.count("hls_root=tapo_camera_hls_dir"),
            5,
        )
        self.assertIn(
            "stream_dir = tapo_camera_hls_dir / safe_key",
            source,
        )
        self.assertIn(
            "@app.get('/api/tapo/camera-hls/"
            "<stream_key>/<path:filename>')",
            source,
        )
        self.assertIn(
            'f"/api/tapo/camera-hls/{key}/index.m3u8"',
            read_source("subsystems/client-tapo/tapo_control.py"),
        )


if __name__ == "__main__":
    unittest.main()
