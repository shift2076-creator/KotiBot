import ast
import os
from pathlib import Path
import shutil
import stat
import subprocess
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def read_source(relative_path):
    path = REPOSITORY_ROOT / relative_path
    source = path.read_text(encoding="utf-8")
    ast.parse(source, filename=str(path))
    return source


class FakeProcess:
    def __init__(self):
        self.running = True
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if self.running else 0

    def terminate(self):
        self.terminated = True
        self.running = False

    def wait(self, timeout):
        self.running = False
        return 0

    def kill(self):
        self.killed = True
        self.running = False


def load_tapo_hls_functions():
    path = (
        REPOSITORY_ROOT
        / "subsystems"
        / "client-tapo"
        / "tapo_control.py"
    )
    tree = ast.parse(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )
    wanted = {
        "tapo_stream_key",
        "start_tapo_camera_stream",
        "stop_tapo_camera_stream",
        "prune_tapo_camera_streams",
    }
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in wanted
    ]
    module = ast.Module(body=selected, type_ignores=[])
    namespace = {
        "Path": Path,
        "os": os,
        "shutil": shutil,
        "subprocess": subprocess,
        "time": time,
        "TAPO_CAMERA_STREAMS": {},
        "TAPO_CAMERA_STREAM_TTL_SECONDS": 45.0,
        "tapo_camera_rtsp_url": (
            lambda client: "rtsp://camera.invalid/stream1"
        ),
        "ffmpeg_rtsp_input": lambda rtsp_url: (
            os.open(os.devnull, os.O_RDONLY),
            "/proc/self/fd/test",
        ),
    }
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


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

    def test_start_replaces_stale_stream_in_external_root(self):
        functions = load_tapo_hls_functions()
        start_stream = functions["start_tapo_camera_stream"]
        stream_key = functions["tapo_stream_key"]
        process = FakeProcess()

        with TemporaryDirectory() as temp_dir:
            hls_root = Path(temp_dir) / "runtime" / "camera-hls"
            hls_root.mkdir(parents=True, mode=0o700)
            key = stream_key("tapo:camera/entry")
            stream_dir = hls_root / key
            stream_dir.mkdir()
            stale_playlist = stream_dir / "index.m3u8"
            stale_playlist.write_text("stale", encoding="utf-8")

            with (
                patch.object(
                    shutil,
                    "which",
                    return_value="/usr/bin/ffmpeg",
                ),
                patch.object(
                    subprocess,
                    "Popen",
                    return_value=process,
                ) as popen,
            ):
                url = start_stream(
                    {"deviceID": "tapo:camera/entry"},
                    hls_root=hls_root,
                )

            self.assertEqual(
                url,
                f"/api/tapo/camera-hls/{key}/index.m3u8",
            )
            self.assertTrue(stream_dir.is_dir())
            self.assertFalse(stale_playlist.exists())
            self.assertEqual(
                stat.S_IMODE(stream_dir.stat().st_mode),
                0o700,
            )

            command = popen.call_args.args[0]
            self.assertIn(
                str(stream_dir / "seg_%05d.ts"),
                command,
            )
            self.assertIn(
                str(stream_dir / "index.m3u8"),
                command,
            )
            self.assertNotIn(
                str(REPOSITORY_ROOT),
                " ".join(command),
            )

    def test_stop_terminates_process_and_removes_stream_tree(self):
        functions = load_tapo_hls_functions()
        stop_stream = functions["stop_tapo_camera_stream"]
        stream_key = functions["tapo_stream_key"]
        streams = functions["TAPO_CAMERA_STREAMS"]
        process = FakeProcess()

        with TemporaryDirectory() as temp_dir:
            hls_root = Path(temp_dir) / "camera-hls"
            hls_root.mkdir()
            key = stream_key("tapo:front-entry")
            stream_dir = hls_root / key
            stream_dir.mkdir()
            (stream_dir / "index.m3u8").write_text(
                "playlist",
                encoding="utf-8",
            )
            streams[key] = {
                "proc": process,
                "dir": stream_dir,
                "last_viewer_at": time.time(),
            }

            stop_stream(
                "tapo:front-entry",
                hls_root=hls_root,
            )

            self.assertTrue(process.terminated)
            self.assertNotIn(key, streams)
            self.assertFalse(stream_dir.exists())

    def test_prune_removes_only_expired_external_stream(self):
        functions = load_tapo_hls_functions()
        prune_streams = functions["prune_tapo_camera_streams"]
        streams = functions["TAPO_CAMERA_STREAMS"]
        expired_process = FakeProcess()
        live_process = FakeProcess()
        now = time.time()

        with TemporaryDirectory() as temp_dir:
            hls_root = Path(temp_dir) / "camera-hls"
            hls_root.mkdir()
            expired_dir = hls_root / "expired"
            live_dir = hls_root / "live"
            expired_dir.mkdir()
            live_dir.mkdir()
            streams.update({
                "expired": {
                    "proc": expired_process,
                    "dir": expired_dir,
                    "last_viewer_at": now - 60,
                },
                "live": {
                    "proc": live_process,
                    "dir": live_dir,
                    "last_viewer_at": now,
                },
            })

            prune_streams(hls_root=hls_root)

            self.assertTrue(expired_process.terminated)
            self.assertNotIn("expired", streams)
            self.assertFalse(expired_dir.exists())
            self.assertFalse(live_process.terminated)
            self.assertIn("live", streams)
            self.assertTrue(live_dir.is_dir())


if __name__ == "__main__":
    unittest.main()
