#!/usr/bin/env bash
# PiVault Cinema — up to 12 new films a day in total, by Pennsylvania calendar day.
# Downloads use curl from Bash. Python 3 only reads LoC metadata.
# No media is re-encoded, zipped, replaced, or automatically removed.

BASE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/home/snx/pi-services/cinema"
VIDEO_DISK="/srv/disk3"
VIDEO_ROOT="$VIDEO_DISK/videos"
NOTIFICATION_ROOT="/srv/pi-server/config/notifications"
export TZ=America/New_York

log() { printf '[%s] %s\n' "$(date '+%F %T %Z')" "$*"; }
die() { log "ERROR: $*" >&2; return 1; }

host_check() {
    (( EUID != 0 )) || { die 'Run as snx, not with sudo.'; return 1; }
    mountpoint -q -- "$VIDEO_DISK" || { die "$VIDEO_DISK is not mounted."; return 1; }
}

catalogue() {
    printf 'PiVault Americana — %s films in the queue\n' "$(queue | wc -l)"
    printf 'Existing comparison: Shadow of a Doubt (1943); Spellbound (1945).\n'
    printf 'Each film is downloaded only once, under its primary genre.\n\n'
    local gib minutes height bitrate
    while IFS=$'\t' read -r genre key title year url size hash loc reason rights minutes height; do
        gib=$(awk -v n="$size" 'BEGIN {printf "%.2f",n/1073741824}')
        bitrate=$(awk -v n="$size" -v m="$minutes" 'BEGIN {printf "%.2f",n*8/(m*60*1000000)}')
        printf '%s | %s (%s) | %s min | %.2f GiB | %sp | %s Mbps\n  %s\n  Archive: %s\n  Rights basis: %s\n' \
            "$genre" "$title" "$year" "$minutes" "$gib" "$height" "$bitrate" "$reason" "$url" "$rights"
    done < <(queue)
}

preview() {
    local genre key title year url size hash loc reason rights minutes height gib bitrate total=0
    declare -A shown=()
    printf 'FIRST ROUND — archive fallback sizes (LoC files may differ)\n'
    while IFS=$'\t' read -r genre key title year url size hash loc reason rights minutes height; do
        [[ -z "${shown[$genre]:-}" ]] || continue
        shown[$genre]=1
        gib=$(awk -v n="$size" 'BEGIN {printf "%.2f",n/1073741824}')
        bitrate=$(awk -v n="$size" -v m="$minutes" 'BEGIN {printf "%.2f",n*8/(m*60*1000000)}')
        printf '%-24s %-42s %6s min  %5s GiB  %5s Mbps\n' "$genre" "$title ($year)" "$minutes" "$gib" "$bitrate"
        total=$((total+size))
    done < <(queue)
    awk -v n="$total" 'BEGIN {printf "Archive fallback total: %.2f GiB\n",n/1073741824}'
}

valid_file() {
    local file=$1 expected=$2 hash=$3 got
    [[ -f "$file" ]] || return 1
    [[ "$(stat -c %s -- "$file")" == "$expected" ]] || return 1
    if [[ "$hash" != - ]]; then
        got=$(md5sum -- "$file") || return 1
        [[ "${got%% *}" == "$hash" ]] || return 1
    else
        # LoC does not consistently publish a checksum; require the MP4 signature.
        [[ "$(dd if="$file" bs=1 skip=4 count=4 status=none 2>/dev/null)" == ftyp ]] || return 1
    fi
}

loc_source() {
    local item=$1 metadata=$2 output headers
    [[ "$item" != - ]] || return 1
    curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
        --connect-timeout 15 --max-time 40 --max-filesize 10485760 \
        --output "$metadata" "${item}?fo=json" 2>/dev/null || return 1
    output=$(python3 - "$metadata" <<'PY'
import json, sys, urllib.parse
try:
    obj=json.load(open(sys.argv[1])); found={}
    def walk(value):
        if isinstance(value, dict):
            url=value.get('url', '')
            if isinstance(url, str):
                parsed=urllib.parse.urlsplit(url)
                if parsed.scheme=='https' and (parsed.hostname or '').endswith('.loc.gov') and parsed.path.lower().endswith('.mp4'):
                    try: score=int(value.get('width',0) or 0)*int(value.get('height',0) or 0)
                    except (TypeError,ValueError): score=0
                    try: height=int(value.get('height',0) or 0)
                    except (TypeError,ValueError): height=0
                    if height > 0: found[url]=max((score,height),found.get(url,(0,0)))
            for v in value.values(): walk(v)
        elif isinstance(value,list):
            for v in value: walk(v)
    walk(obj.get('resources',[]))
    if not found: sys.exit(1)
    url=max(found,key=found.get)
    print(url+'\t'+str(found[url][1]))
except (OSError,ValueError): sys.exit(1)
PY
    ) || return 1
    IFS=$'\t' read -r output LOC_HEIGHT <<< "$output"
    headers=$(curl --fail --silent --show-error --head --location --proto '=https' --proto-redir '=https' \
        --connect-timeout 15 --max-time 40 "$output" 2>/dev/null) || return 1
    LOC_SIZE=$(printf '%s\n' "$headers" | awk 'tolower($1)=="content-length:" {gsub("\r", "", $2); n=$2} END {print n}')
    [[ "$LOC_SIZE" =~ ^[1-9][0-9]*$ ]] || return 1
    LOC_URL=$output
}

daily_count() {
    # Films added today across the whole catalogue (the daily limit is per day, not per genre).
    local file url size hash day genre count=0
    for file in "$BASE"/state/*.done; do
        [[ -f "$file" ]] || continue
        IFS=$'\t' read -r url size hash day genre < "$file"
        if [[ "$day" == "$RUN_DAY" ]]; then count=$((count+1)); fi
    done
    printf '%s\n' "$count"
}

prepare_rights() {
    python3 "$BASE/cinema-rights.py" --evidence "$BASE/rights-evidence" \
        --key "$1" --provider "$2" --url "$3" --bytes "$4" --md5 "$5" \
        --loc-metadata "$BASE/state/$1.loc.json" --records "$BASE/candidate-records.json" --output "$6"
}

transfer() {
    local key=$1 title=$2 year=$3 url=$4 size=$5 hash=$6 provider=$7 genre=$8 source_height=$9
    local part="$VIDEO_ROOT/.pivault-incoming/${key}.${provider}.part"
    local folder="$VIDEO_ROOT/$title ($year)" final="$VIDEO_ROOT/$title ($year)/$title ($year).mp4"
    local have=0 used remaining free summary rights_bytes
    local dossier="$BASE/state/$key.$provider.rights"
    if [[ -f "$final" ]]; then
        die "Existing target left untouched: $final"
        return 1
    fi
    python3 "$BASE/cinema-notifications.py" check --root "$NOTIFICATION_ROOT" \
        --flag "$BASE/state/$key.flag.json" --key "$key" --genre "$genre" \
        --title "$title" --year "$year" --url "$url" --md5 "$hash" --bytes "$size" \
        --minutes "$minutes" --height "$source_height" --tolerance "$TOLERANCE_PERCENT"
    local preflight_status=$?
    (( preflight_status == 0 )) || return "$preflight_status"
    prepare_rights "$key" "$provider" "$url" "$size" "$hash" "$dossier" || { die "Cannot preserve rights evidence for $title; download stopped."; return 1; }
    rights_bytes=$(du -sb -- "$dossier" | awk '{print $1}') || return 1
    [[ ! -f "$part" ]] || have=$(stat -c %s -- "$part")
    if (( have > size )); then
        die "Partial file is larger than the published source: $part. It was left untouched."
        return 1
    fi
    used=$(du -sb -- "$VIDEO_ROOT" | awk '{print $1}') || return 1
    free=$(df -B1 --output=avail -- "$VIDEO_ROOT" | awk 'NR==2 {print $1}') || return 1
    remaining=$((size-have+rights_bytes+8192))
    summary=$(awk -v n="$size" -v m="$minutes" 'BEGIN {printf "%.2f GiB; reference runtime %s min; approx %.2f Mbps",n/1073741824,m,n*8/(m*60*1000000)}')
    log "Preflight $title ($year), $provider: $summary."
    if (( used + remaining > CAP_BYTES )); then
        log "CAP: $title ($year) will not fit under the configured Videos limit."
        return 3
    fi
    if (( free < remaining )); then
        log "SPACE: insufficient free disk space for $title ($year)."
        return 3
    fi
    if (( have < size )); then
        log "Downloading $title ($year) from $provider."
        curl --fail --location --show-error --proto '=https' --proto-redir '=https' \
            --connect-timeout 30 --speed-limit 1024 --speed-time 180 \
            --retry 3 --retry-delay 10 --max-filesize "$size" --continue-at - \
            --output "$part" "$url" || return 1
    fi
    if ! valid_file "$part" "$size" "$hash"; then
        die "Verification failed; partial retained for inspection: $part"
        return 1
    fi
    mkdir -p -- "$folder/rights" || return 1
    cp -a -- "$dossier/." "$folder/rights/" || return 1
    mv -n -- "$part" "$final" || return 1
    [[ ! -e "$part" ]] || { die "Target appeared during download; left untouched: $final"; return 1; }
    printf '%s\t%s\t%s\t%s\t%s\n' "$url" "$size" "$hash" "$RUN_DAY" "$genre" > "$BASE/state/$key.done.tmp" || return 1
    mv -- "$BASE/state/$key.done.tmp" "$BASE/state/$key.done" || return 1
    log "Verified: $title ($year)."
    return 0
}

run_round() {
    local mode=$1 genre key title year url size hash loc reason rights minutes height result status
    local failures=0 new=0 flags=0
    [[ -f "$BASE/cinema.conf" ]] || { die 'Install this script first.'; return 1; }
    # This file is generated locally by install, containing only CAP_BYTES.
    source "$BASE/cinema.conf" || return 1
    host_check || return 1
    mkdir -p -- "$BASE/state" "$VIDEO_ROOT/.pivault-incoming" || return 1
    exec 9>"$BASE/state/run.lock" || return 1
    flock -n 9 || { die 'A cinema round is already running.'; return 75; }
    # Refresh the candidate queue from the archive; a failed lookup keeps yesterday's queue.
    python3 "$BASE/cinema-candidates.py" "$BASE/candidates.txt" "$BASE/queue.tsv.tmp" || log "Candidate lookup returned no films; using the existing queue."
    [[ -f "$BASE/queue.tsv.tmp" ]] && mv -- "$BASE/queue.tsv.tmp" "$BASE/queue.tsv"
    [[ -s "$BASE/queue.tsv" ]] || { die 'No queue yet; run the candidate lookup again.'; return 1; }
    touch "$BASE/state/completed.tsv" || return 1
    RUN_DAY=$(date +%F)
    declare -A chosen=() all_genres=() pending_genres=()
    local daily_limit=12 limit_reached=0
    log "Starting $mode: up to $daily_limit new films for $RUN_DAY."
    while IFS=$'\t' read -r genre key title year url size hash loc reason rights minutes height; do
        all_genres[$genre]=1
        if (( $(daily_count) >= daily_limit )); then
            limit_reached=1
            log "Daily limit of $daily_limit films reached for $RUN_DAY."
            break
        fi
        if [[ -f "$BASE/state/$key.done" && -s "$VIDEO_ROOT/$title ($year)/$title ($year).mp4" ]]; then
            continue
        fi
        python3 "$BASE/cinema-notifications.py" pending --root "$NOTIFICATION_ROOT" --flag "$BASE/state/$key.flag.json"
        status=$?
        if (( status == 5 )); then continue; fi
        if (( status == 4 )); then pending_genres[$genre]=1; continue; fi
        if (( status != 0 )); then
            chosen[$genre]=1
            failures=$((failures+1))
            log "$genre: its review state could not be read; left untouched."
            continue
        fi
        # A previously downloaded copy at the exact final path is never replaced.
        if [[ -f "$VIDEO_ROOT/$title ($year)/$title ($year).mp4" ]]; then
            if valid_file "$VIDEO_ROOT/$title ($year)/$title ($year).mp4" "$size" "$hash"; then
                printf '%s\t%s\t%s\t%s\t%s\n' "$url" "$size" "$hash" existing "$genre" > "$BASE/state/$key.done.tmp" || return 1
                mv -- "$BASE/state/$key.done.tmp" "$BASE/state/$key.done" || return 1
                log "Already present: $title ($year); no download needed."
                continue
            fi
            chosen[$genre]=1
            failures=$((failures+1))
            log "Existing movie differs from queue transfer; left untouched: $title ($year)."
            continue
        fi
        chosen[$genre]=1
        result=1
        LOC_URL= LOC_SIZE=
        if loc_source "$loc" "$BASE/state/$key.loc.json"; then
            transfer "$key" "$title" "$year" "$LOC_URL" "$LOC_SIZE" - loc "$genre" "$LOC_HEIGHT"
            result=$?
        elif [[ "$loc" != - ]]; then
            log "LoC download unavailable for $title; using its pinned archive transfer."
        fi
        if (( result != 0 && result != 4 && result != 5 )); then
            transfer "$key" "$title" "$year" "$url" "$size" "$hash" archive "$genre" "$height"
            result=$?
        fi
        if (( result == 4 )); then
            flags=$((flags+1))
            pending_genres[$genre]=1
            unset 'chosen[$genre]'
            continue
        fi
        if (( result == 5 )); then unset 'chosen[$genre]'; continue; fi
        if (( result == 0 )); then
            printf '%s\t%s\t%s\n' "$RUN_DAY" "$genre" "$key" >> "$BASE/state/completed.tsv" || return 1
            new=$((new+1))
        else
            failures=$((failures+1))
            log "$genre: incomplete; its next attempt will resume the same film."
        fi
    done < <(queue)
    # When the daily limit stopped the round, the rest of the queue is simply for tomorrow.
    if (( ! limit_reached )); then
        for genre in "${!all_genres[@]}"; do
            if [[ -z "${chosen[$genre]:-}" ]]; then
                if [[ -n "${pending_genres[$genre]:-}" ]]; then
                    log "$genre: all remaining candidates require admin review."
                    [[ "$mode" != test ]] || failures=$((failures+1))
                else
                    log "$genre: queue complete."
                fi
            fi
        done
    fi
    log "Round result: $new new; $flags new flags; $failures incomplete."
    (( failures == 0 ))
}

install_cinema() {
    local cap=${1:-} service timer
    [[ "$cap" =~ ^[1-9][0-9]{0,5}$ ]] || { die 'Usage: bash PiVault-Cinema.sh install CAP_IN_GiB'; return 1; }
    host_check || return 1
    [[ -f "$BASE/cinema-rights.py" && -f "$BASE/rights-evidence/catalogue.json" ]] || { die 'Keep the rights helper and rights-evidence folder beside the installer.'; return 1; }
    mkdir -p -- "$INSTALL_DIR/state" "$INSTALL_DIR/rights-evidence" "$VIDEO_ROOT" || return 1
    if [[ "$BASE/PiVault-Cinema.sh" != "$INSTALL_DIR/PiVault-Cinema.sh" ]]; then
        cp -- "${BASH_SOURCE[0]}" "$INSTALL_DIR/PiVault-Cinema.sh" || return 1
        cp -- "$BASE/cinema-notifications.py" "$INSTALL_DIR/cinema-notifications.py" || return 1
        cp -- "$BASE/cinema-rights.py" "$INSTALL_DIR/cinema-rights.py" || return 1
        cp -- "$BASE/cinema-candidates.py" "$INSTALL_DIR/cinema-candidates.py" || return 1
        cp -- "$BASE/candidates.txt" "$INSTALL_DIR/candidates.txt" || return 1
        cp -a -- "$BASE/rights-evidence/." "$INSTALL_DIR/rights-evidence/" || return 1
    fi
    printf 'CAP_BYTES=%s\nTOLERANCE_PERCENT=75\n' "$((cap*1024*1024*1024))" > "$INSTALL_DIR/cinema.conf" || return 1
    sudo install -d -o snx -g "$(id -gn)" -m 0750 "$NOTIFICATION_ROOT" "$NOTIFICATION_ROOT/inbox" "$NOTIFICATION_ROOT/decisions" || return 1
    chmod 700 "$INSTALL_DIR/PiVault-Cinema.sh" || return 1
    service=$(cat <<'UNIT'
[Unit]
Description=PiVault Americana cinema downloads
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=snx
WorkingDirectory=/home/snx/pi-services/cinema
Environment=HOME=/home/snx
ExecStart=/usr/bin/bash /home/snx/pi-services/cinema/PiVault-Cinema.sh run
TimeoutStartSec=infinity
UNIT
    )
    timer=$(cat <<'UNIT'
[Unit]
Description=PiVault cinema daily at 02:00 America/New_York

[Timer]
OnCalendar=*-*-* 02:00:00 America/New_York
AccuracySec=1s
Persistent=false
Unit=pivault-cinema.service

[Install]
WantedBy=timers.target
UNIT
    )
    printf '%s\n' "$service" | sudo tee /etc/systemd/system/pivault-cinema.service >/dev/null || return 1
    printf '%s\n' "$timer" | sudo tee /etc/systemd/system/pivault-cinema.timer >/dev/null || return 1
    sudo systemctl daemon-reload || return 1
    sudo systemctl disable --now pivault-cinema.timer || return 1
    preview
    log "Installed with a $cap GiB Videos cap. Starting the real first-round test (up to 17 films)."
    if ! bash "$INSTALL_DIR/PiVault-Cinema.sh" test; then
        die 'First-round test is incomplete. Nightly scheduling remains disabled. Fix the reported problem, then rerun install with the same cap to resume.'
        return 1
    fi
    sudo systemctl enable --now pivault-cinema.timer || return 1
    log 'First-round test passed. Daily downloads are enabled for 02:00 America/New_York.'
    systemctl list-timers --all pivault-cinema.timer --no-pager
}

# The fixed, reviewed title queue is appended below. No runtime movie searches.

queue() {
    # Rows come from queue.tsv, written by cinema-candidates.py from candidates.txt.
    cat -- "$BASE/queue.tsv"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    case "${1:-}" in
        install) install_cinema "${2:-}" ;;
        run) run_round nightly ;;
        test) run_round test ;;
        catalogue|list) catalogue ;;
        preview) preview ;;
        *)
            printf '%s\n' 'Usage:' \
                '  bash PiVault-Cinema.sh catalogue       # Read every queued selection and its reasons.' \
                '  bash PiVault-Cinema.sh preview         # Show the 17-film first round, sizes and runtimes.' \
                '  bash PiVault-Cinema.sh install 150     # On pivault: install, test one per genre, then schedule.' \
                '  bash ~/pi-services/cinema/PiVault-Cinema.sh test  # Resume an incomplete test.'
            ;;
    esac
fi
