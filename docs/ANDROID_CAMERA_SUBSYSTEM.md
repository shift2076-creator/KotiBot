# KotiBot Android Camera Subsystem

**Authoritative server/browser source:** `2ac56c251d042321373205ec32fd75325d267232`  
**Android client source snapshot:** user-supplied `Files You Need.zip` accompanying this documentation pass  
**Purpose:** Preserve the Android camera subsystem as an explicit architectural and functional contract so camera features are not removed or broken accidentally.

> This document describes the current implementation and the product invariants that future changes must preserve. It does not mark SEC-005 complete and does not itself change runtime behavior.

---

## 1. Product contract

An Android device provisioned with the `CAM` capability is a first-class KotiBot camera. On the Monitor page it must remain distinguishable from a Tapo camera while preserving the common camera-card experience.

Required Android-camera behavior:

- The camera appears on the **Monitor** page when provisioned, assigned to a zone, and carrying the `CAM` role/capability.
- The card displays the current preview when preview delivery is active.
- The card retains the **recording control**.
- The card retains the **camera-talk microphone control** for supported dashboard viewers.
- The settings path retains Android-camera controls such as recording, motion detection, motion threshold, camera selection, preview aspect, motion flashlight, and motion-screen behavior.
- Camera talk remains Android-camera-only; it must not be accidentally enabled for Tapo cameras.
- Camera talk signaling remains ephemeral. ICE candidates and SDP must not be persisted into notification history or ordinary state.
- Uploads and device-side camera-talk endpoints remain device-signed.
- Dashboard camera-talk endpoints remain dashboard-authenticated and same-origin protected for unsafe methods.
- Recordings and transcode staging remain outside the source tree under the configured runtime/media roots.
- Removing or changing any one of these capabilities requires an explicit product decision, not incidental renderer/refactor fallout.

### Known current mismatch at this source

The Android camera renderer still contains the microphone button markup, but it renders that markup only when:

```text
window.shouldRenderAndroidCameraTalkButton(camera) == true
```

The current `shouldRenderAndroidCameraTalkButton()` implementation begins by requiring the **viewer itself to be the Android KEY client app**.

As a result, a normal authenticated dashboard browser can show an Android camera card on Monitor while omitting the talk button.

This is a **known current behavior/mismatch**, not a documented product requirement. The user has identified the missing Monitor-page talk control as accidental. Future repair should change the owning capability/visibility rule rather than reimplementing the button markup elsewhere.

---

## 2. Ownership map

### Server/browser source

| Responsibility | Owning file |
|---|---|
| Android camera/door HTTP routes, preview viewer request, camera commands | `subsystems/client-android-home/client_android_home_routes.py` |
| Android telemetry, frame handling, server-side motion state, camera motion automations | `subsystems/client-android-home/client_android_home_telemetry.py` |
| Android camera/door/motion card rendering | `subsystems/client-android-home/static/js/client-android-home-render.js` |
| Browser camera-talk state machine and WebRTC | `subsystems/voice/static/js/voice-actions.js` |
| Browser camera-talk HTTP API helpers | `subsystems/voice/static/js/voice-api.js` |
| Server camera-talk sessions, ICE/TURN delivery, dashboard/client endpoints | `subsystems/voice/voice_routes.py` |
| Notification/FCM dispatch and durable-history choice | `subsystems/notifications/kotibot_push.py` |
| Status snapshot consumed by dashboard | `server_core/status.py` |
| Android durable-state selection | `server_core/state.py` |
| Recording upload, media validation, rotation normalization, playback | `subsystems/video/video_routes.py` |
| Dashboard camera classification/layout and shared card sync | `static/js/dashboard-render.js` |
| Viewer/platform and Android capability helpers | `static/js/dashboard-utils.js` |
| Dashboard security policy | `subsystems/security/security_routes.py` |

### Android application source snapshot

The Android-side snapshot supplied with this pass contains:

- `SecurityCameraService.kt`
- `KotiBotFirebaseMessagingService.kt`
- `NetworkClient.kt`
- `TLMService.kt`
- `HandshakeService.kt`
- `DoorMonitorService.kt`
- `BootReceiver.kt`
- `MainActivity.kt`
- `Logger.kt`
- `AndroidManifest.xml`
- `build.gradle.kts`
- `settings.gradle.kts`

The three central camera files are:

| Responsibility | Android file |
|---|---|
| CameraX preview/frame/motion/recording + WebRTC receive path | `SecurityCameraService.kt` |
| FCM preview and camera-talk wake/dispatch | `KotiBotFirebaseMessagingService.kt` |
| Signed server requests, recording/frame upload, camera-talk client API | `NetworkClient.kt` |

---

## 3. Role and service lifecycle

Android role configuration is normalized into the app-side role values:

- `camera` → `CAM`
- `door` → `DSS`
- `both` → `CAM` + `DSS`
- `waiting` → unprovisioned/waiting state

`NetworkClient.handleServerConfig()` reconciles Android services when the assigned role changes.

Current service ownership:

```text
waiting
  └─ HandshakeService

door
  └─ DoorMonitorService

camera
  ├─ TLMService
  └─ SecurityCameraService

both
  ├─ TLMService
  ├─ SecurityCameraService
  └─ DoorMonitorService
```

`SecurityCameraService` is a foreground `LifecycleService`. It is declared as a camera/microphone foreground service and is not exported.

The service is sticky. On startup it:

1. Creates/uses the foreground notification.
2. Handles any incoming camera-talk intent.
3. Ensures the CameraX provider exists.
4. Loads current camera configuration from `system_prefs`.

If the client role changes away from `camera` or `both`, the camera service stops itself.

---

## 4. Android permissions and dependencies

The Android manifest declares camera and microphone hardware as optional features and requests:

- `CAMERA`
- `RECORD_AUDIO`
- `MODIFY_AUDIO_SETTINGS`
- camera/microphone foreground-service permissions
- `INTERNET`
- `ACCESS_NETWORK_STATE`
- `WAKE_LOCK`
- notification and boot permissions

The camera service is declared with:

```text
foregroundServiceType="camera|microphone"
```

The Android build uses:

- CameraX core
- CameraX Camera2
- CameraX lifecycle
- CameraX view
- CameraX video
- WebRTC Android SDK
- Firebase Messaging
- AndroidX lifecycle service

### Security invariant

Camera/microphone permission failure must degrade explicitly. Do not bypass Android permission checks or weaken the foreground-service declaration to make a feature appear functional.

---

## 5. Monitor-page render path

The dashboard path is:

```text
/api/status or status stream
        ↓
server_core/status.py
        ↓
S.currentClients
        ↓
static/js/dashboard-render.js
        ↓
dashboardClientIsCamera()
        ↓
window.renderCameraCard()
        ↓
client-android-home-render.js
```

For Monitor mode, the shared dashboard renderer admits camera clients and calls the Android Home camera renderer.

`renderCameraCard()` first delegates Tapo cameras to the Tapo camera renderer. Otherwise it renders the Android camera card.

The Android card currently owns:

- camera title/subtitle
- camera state icon
- battery display
- microphone/talk control
- recording control
- settings menu
- preview image
- debug/status area

### Talk-button render chain

```text
renderCameraCard(camera)
        ↓
shouldRenderAndroidCameraTalkButton(camera)
        ↓
viewer type + provisioned + stale + CAM/TAPO checks
        ↓
talk button HTML or empty string
```

The button markup itself is already present in the renderer:

```text
class="icon-btn camera-talk-btn"
data-camera-talk-button="1"
data-device-id="<camera>"
```

The browser talk implementation binds at the document level to `data-camera-talk-button`, so the button does not need a second dashboard action-handler implementation.

### Current visibility gate

Current visibility requires all of the following:

- viewer is detected as the Android KEY client app
- camera is provisioned
- camera is not stale
- camera has `CAM`
- camera is not Tapo
- `cameraTalkAvailable` / `camera_talk_available` is not explicitly false

The **viewer-is-Android-KEY** condition is the current reason a normal browser can have no talk button even though the Android camera supports talk.

Do not repair this by duplicating the button in `dashboard-render.js`. The owning fix belongs in the camera-talk capability/visibility rule.

---

## 6. Preview path

### Dashboard → server

When a camera is visible, the dashboard tracks a preview viewer through:

```text
POST /api/preview-viewer
```

The server keeps transient preview-viewer membership and computes `preview_requested`.

When the first viewer arrives or the last viewer leaves, KotiBot can notify the Android camera through FCM using the `preview_request` event.

### Server → Android

`KotiBotFirebaseMessagingService` handles:

```text
preview_request / PREVIEW_REQUEST
```

It updates `system_prefs.previewRequested`. When preview becomes active it starts `SecurityCameraService` as a foreground service if needed.

### Android camera pipeline

`SecurityCameraService.updateCameraState()` binds CameraX only when at least one of these is required:

- preview
- recording
- motion detection

When none is required it unbinds camera use cases, releases the camera wake lock, stops active recording, and clears motion sampling state.

This conditional pipeline is an efficiency invariant. Do not keep CameraX running merely to simplify UI state.

### Frame production

The CameraX `ImageAnalysis` path:

- uses `STRATEGY_KEEP_ONLY_LATEST`
- performs camera warmup/stability gating
- rotates frames for display/upload
- uploads frames when preview or recording requires them
- limits frame uploads to two concurrent uploads
- currently uses roughly a 900 ms upload interval
- separately samples motion when motion detection is enabled

Server-side `/video_feed/<deviceID>` returns the latest in-memory frame for a `CAM` client.

The status snapshot supplies:

```text
latest_frame_url
frame_live
frame_age
preview_requested
```

The Android camera card uses that preview URL.

---

## 7. Camera commands and settings

Dashboard camera settings flow through:

```text
POST /api/client-command
```

Current Android-camera command/state fields include:

- `recordingEnabled`
- `motionDetectionEnabled`
- `motionDetectionThreshold`
- `motionFlashlightEnabled`
- `motionScreenEnabled`
- `selectedCamera`
- `previewAspect`
- name/zone changes
- enabled roles

The server puts pending commands/state into the Android camera client. Android telemetry/server responses update `system_prefs`, and `SecurityCameraService` reacts through its preference listener.

### Camera selection

`selectedCamera` is normalized to:

- `front`
- `back`

Changing lens or aspect can rebuild the CameraX pipeline.

### Orientation

The Android service listens for orientation changes and updates CameraX target rotation. Recording can be restarted when target rotation changes so the next segment has the correct orientation contract.

---

## 8. Recording path

### Dashboard control

The Android camera card includes a recording button whose state is based on:

```text
recording_enabled
```

Changing it goes through the Android client command path.

### Android recording

Android uses CameraX `Recorder`/`VideoCapture`.

Current behavior:

- recording is segmented
- current segment duration is approximately 15 seconds
- audio is included when microphone permission is available
- local segment files are uploaded after finalization
- recording continues with the next segment while enabled

### Upload

Android uploads recording segments to:

```text
POST /upload_video
```

The request is device-signed and includes the established device identity.

Server-side `video_routes.py`:

- takes authoritative identity from `g.kotibot_device_id`
- rejects a conflicting form `deviceID`
- requires a provisioned `CAM` client
- validates the media container signature
- writes under the configured recording root
- uses private directory/file modes on POSIX
- optionally normalizes rotation with ffprobe/ffmpeg
- uses the configured transient transcode directory
- never needs the repository as the media destination

### Runtime-path invariant

Recordings and transcode products must stay outside the source tree. A future Android-camera change must not introduce source-relative recording, staging, cache, or temp paths.

---

## 9. Motion detection path

Android camera motion has both Android-side and server-side state handling.

### Android-side work

`SecurityCameraService` performs lightweight local frame sampling:

- current sample grid: 16 × 12
- current check interval: about 300 ms
- configured threshold default: 18
- repeated motion reporting is bounded
- a lighting/flashlight settle window prevents immediate false samples

When local motion is detected it can:

- start recording
- request flashlight behavior
- request screen behavior
- send camera-motion telemetry

### Server-side work

`client_android_home_telemetry.py`:

- updates active/last-motion state
- records activity on the initial transition
- fires configured camera-motion routes
- can set recording/pending commands
- schedules recording stop after the motion idle window
- avoids repeatedly firing the same initial activity transition

The current server motion-recording idle window is approximately 15 seconds.

### Efficiency invariant

Do not replace current bounded/event-driven motion handling with frequent global polling or duplicate image analysis paths.

---

## 10. Camera talk: browser → Android end-to-end

Camera talk is WebRTC audio from the dashboard viewer to the Android camera device.

### High-level flow

```text
Monitor Android camera card
        ↓
microphone button
        ↓
voice-actions.js
        ↓
browser microphone via getUserMedia()
        ↓
POST /api/voice/session
        ↓
server creates in-memory talk session
        ↓
offer + dashboard ICE candidates
        ↓
FCM camera_talk_request / camera_talk_candidate
        ↓
KotiBotFirebaseMessagingService
        ↓
SecurityCameraService
        ↓
Android WebRTC peer connection / speaker output
        ↓
answer + Android ICE candidates
        ↓
device-signed /api/camera-talk/client/... endpoints
        ↓
server in-memory session
        ↓
browser receives answer/client candidates
```

### Browser owner

`subsystems/voice/static/js/voice-actions.js` owns:

- microphone acquisition
- secure-context requirement
- preferred echo/noise/AGC constraints
- fallback to bare audio for selected device/constraint errors
- `RTCPeerConnection`
- browser offer
- dashboard ICE candidate posting
- server-session polling while active
- applying Android answer/candidates
- connection timeout
- button active/pending state
- teardown
- `pagehide` cleanup

The current active session poll interval is about 250 ms. This is active-session work, not an always-on dashboard poll.

### Browser API owner

`subsystems/voice/static/js/voice-api.js` owns dashboard-side requests:

```text
POST /api/voice/session
POST /api/voice/session/<sessionID>/offer
POST /api/voice/session/<sessionID>/candidate
GET  /api/voice/session/<sessionID>
POST /api/voice/session/<sessionID>/end
```

### Server owner

`subsystems/voice/voice_routes.py` stores live sessions in memory and owns:

- session creation and pruning
- SDP validation
- target-camera validation
- dashboard/client candidate exchange
- Android answer/state/end
- STUN/TURN/ICE server delivery
- FCM wake/signaling to Android

A valid target must be:

- provisioned
- `CAM`
- non-Tapo
- non-stale

### Android FCM owner

`KotiBotFirebaseMessagingService` handles:

- `camera_talk_request`
- `camera_talk_candidate`
- `camera_talk_end`

It converts each FCM message into an explicit `SecurityCameraService` action containing only the session/candidate/reason data needed for that action.

### Android WebRTC owner

`SecurityCameraService`:

- allows camera talk only for camera/both roles
- builds the WebRTC factory/audio module
- receives the dashboard offer
- creates a receive-audio peer connection
- routes received audio for communication/speaker playback
- applies dashboard ICE candidates
- queues early candidates until remote description is ready
- creates/posts the answer
- posts Android ICE candidates
- reports connected/failed/ended state
- restores the previous Android audio route when no talk sessions remain
- closes sessions/factory/audio resources during service destruction

---

## 11. Camera-talk notification privacy

Camera-talk signaling is transport data, not durable household history.

### Required contract

`camera_talk_candidate`:

- is delivered through FCM
- is **not** persisted into notification history
- is **not** written to ordinary durable state
- is **not** echoed into general status/debug output

`KotiBotPushQueue.enqueue_data()` supports:

```text
persist_history=False
```

The voice subsystem uses that mode specifically for `camera_talk_candidate`.

The SEC-005 notification-history repair removed historical candidate records that contained network topology information. Future changes must preserve the ephemeral delivery contract.

### Rollback material

The SEC-005 history sanitizer intentionally retained a private recovery copy outside the repository. It is recovery material, not a source asset and not a normal runtime consumer.

---

## 12. Authentication and authorization boundaries

`subsystems/security/security_routes.py` is the security owner.

### Dashboard side

Dashboard camera-talk routes fall through to the default dashboard policy:

```text
/api/voice/...
/api/camera-talk/...     except /client/ prefixes
```

Therefore they require a dashboard session. Unsafe dashboard methods also require the same-origin check.

### Android/device side

These prefixes are explicitly device-signed:

```text
/api/voice/client/
/api/camera-talk/client/
```

Android frame/video upload routes are also device-signed:

```text
/upload_frame
/upload_video
```

`NetworkClient` signs device requests with the Koti device credential using timestamp, nonce, body digest, key ID, and HMAC signature headers.

### Credential boundary

TURN credentials may be returned only as part of the explicitly authorized WebRTC connection setup to the participating peer. They must never be copied to ordinary status, logs, notification history, or durable non-secret state.

---

## 13. Status contract used by the dashboard

For a provisioned Android CAM, `server_core/status.py` currently exposes the non-secret operational state needed for rendering, including:

- canonical `deviceID`
- display name
- provisioned/stale
- battery
- zone
- Android client class/capabilities
- camera-talk available/active
- frame live/age
- recording enabled
- motion enabled/threshold/current state
- motion flashlight/screen settings
- selected camera
- preview aspect
- preview requested
- latest-frame URL

`camera_talk_available` is computed server-side from:

```text
provisioned AND CAM AND not Tapo AND not stale
```

The browser then applies its additional viewer-side visibility gate.

### Privacy invariant

The status payload is a UI contract, not a general diagnostic dump. Do not reintroduce raw IP, MAC, serial, credential, token, raw discovery, recording filesystem path, or arbitrary vendor payloads merely to make debugging easier.

---

## 14. Durable versus ephemeral state

### Durable/user-owned settings

Examples that may legitimately survive restart:

- device display name
- zone
- assigned roles
- deliberate camera/motion configuration where the current durable-state contract calls for it

### Reconstructible/runtime state

Examples that should remain runtime or be reconstructed:

- live frame bytes
- frame age/live state
- preview viewers
- active WebRTC sessions
- ICE candidates
- current talk connection state
- active upload/concurrency counters
- transient CameraX warmup state
- current peer connections/audio routes

### Separate roadmap ownership

Further removal of reconstructible Android telemetry from durable persistence belongs to the STATE-004/STATE-005 roadmap work. Do not use an Android-camera bug fix to silently perform that migration ahead of its dependency chain.

---

## 15. Performance/resource contract

Android camera code runs on resource-constrained always-on hardware. Preserve these properties:

- CameraX is bound only when preview, recording, or motion detection requires it.
- Image analysis uses keep-only-latest backpressure.
- Frame uploads are rate-limited and concurrency-limited.
- Motion sampling is low-resolution and bounded.
- Recording upload is segmented rather than one unbounded in-memory recording.
- FCM wakes the Android camera for preview/talk events instead of adding a server-side high-frequency discovery poll.
- Camera talk polling exists only during an active browser talk session and is torn down immediately afterward.
- Peer connections, microphone tracks, timers, audio routes, and Android camera resources are explicitly released.
- No Android-camera feature should introduce a source-tree write.

A latency or resource regression is a functional defect, not merely an optimization opportunity.

---

## 16. Regression invariants

Future work touching any Android camera file should verify the following.

### Monitor/card

- [ ] Android CAM appears on Monitor.
- [ ] Tapo cameras still use the Tapo renderer.
- [ ] Android preview still renders.
- [ ] Android recording button is present and reflects state.
- [ ] Android camera-talk microphone control is present for the intended supported viewer.
- [ ] Settings menu still opens the Android camera settings path.
- [ ] Camera card survives refresh/status updates without unnecessary recreation.

### Preview

- [ ] Opening Monitor requests preview.
- [ ] Android receives preview request through FCM when needed.
- [ ] Closing/leaving removes the viewer request.
- [ ] Frame delivery stops when no camera consumer requires CameraX.

### Recording

- [ ] Manual record starts/stops.
- [ ] Motion-triggered record still works.
- [ ] Segments upload successfully.
- [ ] Upload identity is device-signed.
- [ ] Recordings land only under external media root.
- [ ] Rotation normalization remains correct.

### Motion

- [ ] Motion enable/disable works.
- [ ] Threshold changes propagate.
- [ ] Motion event fires once on transition, not every frame.
- [ ] Idle timer extends/resets correctly on retrigger.
- [ ] Flashlight/screen options remain bounded.

### Camera talk

- [ ] Microphone button is visible where product policy says it should be.
- [ ] Browser microphone permission is requested only after user action.
- [ ] Talk connects to an Android CAM.
- [ ] Tapo camera cards do not receive Android talk control.
- [ ] Only one dashboard talk target is active at a time.
- [ ] Toggle-off releases microphone, timers, and peer connection.
- [ ] Android restores prior audio routing after talk ends.
- [ ] FCM candidate delivery still works.
- [ ] `camera_talk_candidate` does not enter notification history.
- [ ] ICE/SDP does not enter ordinary durable state.
- [ ] SEC-005 output verifier remains green after an actual talk session.

### Security

- [ ] Dashboard talk endpoints remain dashboard-authenticated.
- [ ] Unsafe dashboard methods retain same-origin enforcement.
- [ ] Android talk/client endpoints remain device-signed.
- [ ] Frame/video uploads remain device-signed.
- [ ] TURN/service credentials remain only at protected issuance/use boundaries.
- [ ] No secret/private values appear in status/log/history/debug output.

---

## 17. Tests and verification surfaces

Current relevant server-side test families include:

- Android role/capability detection
- Android frame upload context
- camera recording indicator/rendering
- media runtime paths
- security route policy
- SEC-005 output sanitization
- SEC-005 notification-history privacy

Any repair to the missing talk button should add a focused renderer/visibility regression proving:

1. an eligible provisioned Android CAM receives a talk button under the intended viewer policy;
2. stale/unprovisioned cameras do not;
3. Tapo cameras do not;
4. the control still carries `data-camera-talk-button`;
5. normal Monitor rendering does not depend on a second duplicated markup path.

Runtime proof still requires:

- real dashboard/browser rendering
- actual Android camera
- actual microphone permission
- WebRTC connection
- FCM signaling
- post-session SEC-005 verification

---

## 18. Current SEC-005 relationship

Automated SEC-005 sanitization checks are green at the time this document was requested, including sanitized notification history and protected credential-state verification.

SEC-005 remains **open** because the final live Android camera-talk functional check could not be performed: the microphone control was missing from the Monitor page.

The missing control must be restored/verified, one real camera-talk session must succeed, and the output sanitizer must remain green afterward before SEC-005 should be marked complete.

---

## 19. Change-review rule for Android camera work

Before accepting an Android-camera change, trace the affected path across all owners rather than reviewing one file in isolation:

```text
dashboard render
  ↕
status/API
  ↕
Android Home routes/telemetry
  ↕
notification/FCM
  ↕
Android service
  ↕
camera / recording / WebRTC
  ↕
signed server endpoints
  ↕
runtime media/state
```

A change that removes a renderer control, status field, FCM event, device endpoint, Android service action, or runtime path can silently disable the whole feature even when unit tests outside that layer remain green.

That is the failure mode this document is intended to prevent.
