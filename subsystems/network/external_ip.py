import ipaddress
import json
import os
from threading import Event
from urllib import request as urlrequest
from urllib import error as urlerror


DEFAULT_CHECK_INTERVAL_SECONDS = 300


def register_external_ip_checker(app, context):
    stop_event = Event()
    cloudflare_api_token = (
        context['integration_credentials'].cloudflare_api_token
    )
    state = {
        'last_seen': '',
        'dns_last_set': '',
    }

    def env_enabled(name, default='0'):
        return str(os.environ.get(name, default)).strip().lower() in ('1', 'true', 'yes', 'on')

    def external_ip_configured():
        return bool(
            env_enabled('KOTIBOT_EXTERNAL_IP_ENABLED')
            and cloudflare_api_token
            and os.environ.get('KOTIBOT_CLOUDFLARE_ZONE_ID')
        )

    def read_url_text(url, timeout=8):
        req = urlrequest.Request(
            url,
            headers={
                'User-Agent': 'KotiBot/1.0',
                'Accept': 'text/plain, application/json',
            },
        )

        with urlrequest.urlopen(req, timeout=timeout) as response:
            return response.read().decode('utf-8', errors='replace').strip()

    def fetch_external_ip():
        record_type = os.environ.get('KOTIBOT_CLOUDFLARE_RECORD_TYPE', 'A').strip().upper() or 'A'
        urls = (
            'https://api.ipify.org',
            'https://ifconfig.me/ip',
            'https://checkip.amazonaws.com',
        )

        last_error = ''

        for url in urls:
            try:
                ip = read_url_text(url)
                parts = ip.split()

                if not parts:
                    continue

                candidate = parts[0].strip()
                parsed = ipaddress.ip_address(candidate)

                if record_type == 'A' and parsed.version == 4:
                    return candidate

                if record_type == 'AAAA' and parsed.version == 6:
                    return candidate

            except Exception as e:
                last_error = str(e)

        raise RuntimeError(last_error or f'Unable to determine external {record_type} IP')

    def cloudflare_request(method, path, payload=None):
        token = cloudflare_api_token

        if not token:
            raise RuntimeError('Missing protected Cloudflare API token')

        body = None

        if payload is not None:
            body = json.dumps(payload).encode('utf-8')

        req = urlrequest.Request(
            f'https://api.cloudflare.com/client/v4{path}',
            data=body,
            method=method,
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'KotiBot/1.0',
            },
        )

        try:
            with urlrequest.urlopen(req, timeout=12) as response:
                return json.loads(response.read().decode('utf-8', errors='replace') or '{}')
        except urlerror.HTTPError as e:
            detail = e.read().decode('utf-8', errors='replace')
            raise RuntimeError(f'Cloudflare HTTP {e.code}: {detail}') from e

    def cloudflare_dns_record(hostname):
        zone_id = os.environ.get('KOTIBOT_CLOUDFLARE_ZONE_ID', '').strip()
        record_id = os.environ.get('KOTIBOT_CLOUDFLARE_RECORD_ID', '').strip()
        record_type = os.environ.get('KOTIBOT_CLOUDFLARE_RECORD_TYPE', 'A').strip().upper() or 'A'

        if not zone_id:
            raise RuntimeError('Missing KOTIBOT_CLOUDFLARE_ZONE_ID')

        if record_id:
            data = cloudflare_request('GET', f'/zones/{zone_id}/dns_records/{record_id}')
            record = data.get('result') or {}

            if not record.get('id'):
                raise RuntimeError('Cloudflare record ID not found')

            return record

        data = cloudflare_request(
            'GET',
            f'/zones/{zone_id}/dns_records?type={record_type}&name={hostname}',
        )

        records = data.get('result') or []

        if not records:
            raise RuntimeError(f'Cloudflare DNS record not found for {hostname}')

        return records[0]

    def update_cloudflare_dns(ip):
        hostname = os.environ.get('KOTIBOT_PUBLIC_HOSTNAME', 'kotibot.app').strip() or 'kotibot.app'
        zone_id = os.environ.get('KOTIBOT_CLOUDFLARE_ZONE_ID', '').strip()
        proxied = env_enabled('KOTIBOT_CLOUDFLARE_PROXIED', '1')
        record = cloudflare_dns_record(hostname)

        if str(record.get('content') or '').strip() == ip and bool(record.get('proxied')) == proxied:
            return False

        payload = {
            'type': record.get('type') or os.environ.get('KOTIBOT_CLOUDFLARE_RECORD_TYPE', 'A').strip().upper() or 'A',
            'name': record.get('name') or hostname,
            'content': ip,
            'ttl': int(record.get('ttl') or 1),
            'proxied': proxied,
        }

        result = cloudflare_request(
            'PUT',
            f'/zones/{zone_id}/dns_records/{record["id"]}',
            payload,
        )

        if not result.get('success'):
            raise RuntimeError(json.dumps(result, separators=(',', ':')))

        return True

    def external_ip_check_once():
        ip = fetch_external_ip()
        configured = external_ip_configured()

        if ip == state['last_seen'] and (not configured or state['dns_last_set'] == ip):
            return

        state['last_seen'] = ip

        if not configured:
            return

        update_cloudflare_dns(ip)
        state['dns_last_set'] = ip

    def external_ip_check_loop():
        if not env_enabled('KOTIBOT_EXTERNAL_IP_ENABLED'):
            return

        try:
            interval_seconds = max(
                60,
                int(
                    os.environ.get('KOTIBOT_EXTERNAL_IP_CHECK_SECONDS', str(DEFAULT_CHECK_INTERVAL_SECONDS))
                    or DEFAULT_CHECK_INTERVAL_SECONDS
                ),
            )
        except (TypeError, ValueError):
            interval_seconds = DEFAULT_CHECK_INTERVAL_SECONDS

        while not stop_event.is_set():
            try:
                external_ip_check_once()
            except Exception:
                app.logger.exception('External IP check failed')

            stop_event.wait(interval_seconds)

    app.config['KOTIBOT_EXTERNAL_IP_STOP'] = stop_event
    app.config['KOTIBOT_EXTERNAL_IP_CHECK_LOOP'] = external_ip_check_loop

    return external_ip_check_loop
