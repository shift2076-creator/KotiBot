import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class TapoPreviewLifecycleTests(unittest.TestCase):
    @staticmethod
    def source(relative_path):
        return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")

    @staticmethod
    def source_block(source, start_marker, end_marker):
        start = source.index(start_marker)
        end = source.index(end_marker, start)
        return source[start:end]

    def setUp(self):
        self.actions_source = self.source(
            "subsystems/client-tapo/static/js/tapo-actions.js"
        )

    def test_player_teardown_destroys_hls_and_resets_video_state(self):
        teardown = self.source_block(
            self.actions_source,
            "function destroyTapoCameraVideoPlayer",
            "function cleanupDetachedTapoCameraPlayers",
        )

        self.assertIn("existing.destroy();", teardown)
        self.assertIn("window.tapoHlsPlayers.delete(video);", teardown)
        self.assertIn("window.tapoHlsPlayerElements.delete(video);", teardown)
        self.assertIn('video.dataset.hlsAttached = "";', teardown)
        self.assertIn('video.dataset.hlsAttaching = "";', teardown)
        self.assertIn('video.dataset.hlsNative = "";', teardown)
        self.assertIn('video.dataset.hlsState = "idle";', teardown)
        self.assertIn("if (options.clearSource)", teardown)
        self.assertIn('video.dataset.hlsSrc = "";', teardown)
        self.assertIn('video.removeAttribute("src");', teardown)
        self.assertIn("if (video.isConnected)", teardown)
        self.assertIn("video.load();", teardown)
        self.assertIn('video.style.display = "none";', teardown)

    def test_detached_cleanup_and_scheduled_sync_are_deduplicated(self):
        cleanup = self.source_block(
            self.actions_source,
            "function cleanupDetachedTapoCameraPlayers",
            "function scheduleTapoCameraVideoSync",
        )
        scheduler = self.source_block(
            self.actions_source,
            "function scheduleTapoCameraVideoSync",
            "function setTapoCameraPreviewActive",
        )

        self.assertIn(
            "Array.from(window.tapoHlsPlayerElements).forEach(video =>",
            cleanup,
        )
        self.assertIn("if (video.isConnected) return;", cleanup)
        self.assertIn(
            "window.tapoCameraViewportObserver?.unobserve?.(video);",
            cleanup,
        )
        self.assertIn("clearSource: true", cleanup)

        self.assertIn(
            "window.__tapoCameraSyncForce = "
            "!!window.__tapoCameraSyncForce || !!force;",
            scheduler,
        )
        self.assertIn(
            "window.clearTimeout(window.__tapoCameraSyncTimer);",
            scheduler,
        )
        self.assertEqual(scheduler.count("window.setTimeout("), 1)
        self.assertLess(
            scheduler.index("cleanupDetachedTapoCameraPlayers();"),
            scheduler.index("window.initTapoCameraVideos?.(shouldForce);"),
        )

    def test_sleep_wake_deduplication_and_heartbeat_are_bounded(self):
        lifecycle = self.source_block(
            self.actions_source,
            "function setTapoCameraPreviewActive",
            "function getTapoCameraVisibilityNode",
        )

        self.assertIn(
            "window.tapoCameraSleepTimers.delete(deviceID);",
            lifecycle,
        )
        self.assertIn(
            "window.tapoCameraPreviewState.get(deviceID) !== true && !force",
            lifecycle,
        )
        self.assertIn(
            "const stillVisible = videos.some(item => "
            "isTapoVideoVisible(item));",
            lifecycle,
        )
        self.assertIn("window.TAPO_CAMERA_SLEEP_DELAY_MS", lifecycle)
        self.assertIn("window.tapoCameraLastWake.delete(deviceID);", lifecycle)
        self.assertIn(
            "window.setTapoPreviewViewer(deviceID, false, useBeacon);",
            lifecycle,
        )
        self.assertIn("window.TAPO_CAMERA_WAKE_DEDUP_MS", lifecycle)
        self.assertIn("window.TAPO_CAMERA_VIEWER_HEARTBEAT_MS", lifecycle)
        self.assertIn(
            "const needsWake = current !== true || "
            "(!recentWake && (force || heartbeatDue));",
            lifecycle,
        )
        self.assertIn("if (!needsWake)", lifecycle)
        self.assertIn(
            "window.tapoCameraLastWake.set(deviceID, now);",
            lifecycle,
        )
        self.assertEqual(
            lifecycle.count(
                "window.setTapoPreviewViewer(deviceID, true, false);"
            ),
            1,
        )

    def test_preview_responses_reset_sources_and_log_failures(self):
        preview_request = self.source_block(
            self.actions_source,
            "window.setTapoPreviewViewer = function",
            "window.tapoHlsPlayers =",
        )

        self.assertIn("if (!data?.ok)", preview_request)
        self.assertIn(
            'console.warn("Tapo camera preview request failed", '
            'data?.error || "unknown error");',
            preview_request,
        )
        self.assertIn("if (!previewUrl)", preview_request)
        self.assertIn("clearSource: true", preview_request)
        self.assertIn("hide: true", preview_request)
        self.assertIn("if (previousSrc !== previewUrl)", preview_request)
        self.assertIn('video.dataset.hlsAttached = "";', preview_request)
        self.assertIn('video.dataset.hlsAttaching = "";', preview_request)
        self.assertIn(
            '.catch(err => {\n      console.warn('
            '"Tapo camera preview request failed", err);',
            preview_request,
        )

    def test_player_attachment_rejects_duplicates_and_stale_async_work(self):
        attachment = self.source_block(
            self.actions_source,
            "window.initTapoCameraVideo = async function",
            "window.tapoCameraViewportObserver =",
        )

        self.assertIn("if (playerAttached)", attachment)
        self.assertIn("if (video.dataset.hlsAttaching === src)", attachment)
        self.assertLess(
            attachment.index("destroyTapoCameraVideoPlayer(video);"),
            attachment.index("video.dataset.hlsAttaching = src;"),
        )
        self.assertIn(
            "if (!video.isConnected || video.dataset.hlsSrc !== src)",
            attachment,
        )
        self.assertIn("window.tapoHlsPlayers.set(video, hls);", attachment)
        self.assertGreaterEqual(
            attachment.count(
                "if (window.tapoHlsPlayers.get(video) !== hls) return;"
            ),
            2,
        )
        self.assertIn("hls.loadSource(src);", attachment)
        self.assertIn("hls.attachMedia(video);", attachment)

    def test_visibility_navigation_and_loader_hooks_remain_single_owner(self):
        hooks = self.source_block(
            self.actions_source,
            "window.tapoCameraViewportObserver =",
            "async function sendTapoCommand",
        )
        dashboard_events = self.source("static/js/dashboard-events.js")
        dashboard_main = self.source("static/js/dashboard-main.js")

        self.assertIn("if (entry.isIntersecting)", hooks)
        self.assertIn(
            "setTapoCameraPreviewActive(video, true, false);",
            hooks,
        )
        self.assertIn(
            "setTapoCameraPreviewActive(video, false, false);",
            hooks,
        )
        self.assertIn(
            "if (window.tapoCameraViewportObserver && "
            "!video.dataset.tapoViewportObserved)",
            hooks,
        )
        self.assertIn(
            'document.addEventListener("visibilitychange"',
            hooks,
        )
        self.assertIn('window.addEventListener("pageshow"', hooks)
        self.assertIn('window.addEventListener("focus"', hooks)
        self.assertIn('window.addEventListener("scroll"', hooks)
        self.assertIn('window.addEventListener("resize"', hooks)
        self.assertIn(
            "window.tapoCameraWakeInterval = "
            "window.tapoCameraWakeInterval || window.setInterval",
            hooks,
        )
        self.assertIn("window.sleepAllTapoCameraVideos?.(true);", dashboard_events)
        self.assertIn(
            "if (dashboardSubsystemScriptPromises.has(key))",
            dashboard_main,
        )
        self.assertIn(
            "return dashboardSubsystemScriptPromises.get(key);",
            dashboard_main,
        )


if __name__ == "__main__":
    unittest.main()
