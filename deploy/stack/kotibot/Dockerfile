# KotiBot for the PiVault stack. Built on pivault from a pinned KotiBot commit; see README.md.
# The base is Debian 13 (trixie) with Python 3.13, the same as the KotiBot 0.8 host it replaces.
FROM python:3.13-slim-trixie

# ffmpeg: Tapo camera streaming and recording. ca-certificates and git: fetching the pinned source.
# bluez: provides bluetoothctl, which KotiBot runs for Bluetooth. It talks to the host's bluetoothd over the host D-Bus
# socket (mounted in the Compose file); no daemon runs in the container.
# The rest are the shared libraries chip-tool needs (from ldd on the Pi 4 build, 2026-11-17). It uses no Avahi.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates git ffmpeg bluez \
    libssl3t64 libglib2.0-0t64 libevent-core-2.1-7t64 libevent-pthreads-2.1-7t64 libstdc++6 libatomic1 \
 && rm -rf /var/lib/apt/lists/*

# Python packages come first and depend only on requirements.txt (a copy of KotiBot's list, checked against the
# pinned source below), so a new KotiBot commit does not reinstall them. requests is added on top: KotiBot imports
# google.auth.transport.requests, but its requirements.txt does not list requests.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
 && pip install --no-cache-dir requests==2.34.2

# Declared after every slow step so a new commit never invalidates them.
# Full commit of github.com/shift2076-creator/KotiBot. Change it together with the image tag in the Compose file.
ARG KOTIBOT_REF=3048de61b9d95f511d0c9a8918f5269e9adbc308

# Source goes in root-owned and read-only to the service user: KotiBot must never write beneath its source tree.
# The build fails if KotiBot's requirements.txt at the pinned commit differs from the copy above.
RUN git clone --quiet https://github.com/shift2076-creator/KotiBot.git /opt/kotibot \
 && git -C /opt/kotibot checkout --quiet "$KOTIBOT_REF" \
 && test "$(git -C /opt/kotibot rev-parse HEAD)" = "$KOTIBOT_REF" \
 && cmp /opt/kotibot/requirements.txt /tmp/requirements.txt \
 && rm -rf /opt/kotibot/.git /tmp/requirements.txt \
 && apt-get purge -y --auto-remove git

# CSA production attestation roots for chip-tool (see paa-root-certs/README.md). Without them, production Matter
# devices fail commissioning with "Failed Device Attestation".
COPY paa-root-certs/ /opt/matter-paa/

WORKDIR /opt/kotibot

# Runtime state lives outside the source tree. The Compose file mounts /data and /credentials and
# gives /cache and /run/kotibot as tmpfs. Every path must be absolute and writable only by the service user.
ENV KOTIBOT_DATA_DIR=/data \
    KOTIBOT_CACHE_DIR=/cache \
    KOTIBOT_RUNTIME_DIR=/run/kotibot \
    KOTIBOT_CREDENTIALS_DIR=/credentials \
    KOTIBOT_MATTER_CHIP_TOOL=/opt/chip-tool/chip-tool \
    KOTIBOT_MATTER_PAA_TRUST_STORE=/opt/matter-paa \
    KOTIBOT_LISTEN=127.0.0.1:5000 \
    PYTHONDONTWRITEBYTECODE=1

USER 1000:1000

# Same server as the kotibot.service unit on the Pi 4: waitress, 12 threads. Do not add worker processes,
# because KotiBot keeps device workers and state in one process.
CMD ["sh", "-c", "exec waitress-serve --listen=\"$KOTIBOT_LISTEN\" --threads=12 wsgi:application"]
