import heapq
import time
from pathlib import Path
from threading import Lock

from server_core.io import (
    JsonStateReadError,
    read_json_object,
    write_json_atomic,
)

class KotiBotActivityLog:
    CATEGORIES = ('automation', 'security', 'system', 'users')
    ACTIVITY_BUCKETS = (
        'day_0_previous_24_hours',
        'day_1_yesterday',
        'day_2_two_days_ago',
        'day_3_three_days_ago',
        'day_4_four_days_ago',
        'day_5_five_days_ago',
        'day_6_six_days_ago',
    )
    BUCKET_SECONDS = 24 * 60 * 60

    def __init__(self, state_file, max_events=200, clients=None):
        self.state_file = Path(state_file)
        try:
            self.max_events = max(1, int(max_events or 200))
        except Exception:
            self.max_events = 200

        self.clients = clients if isinstance(clients, dict) else {}
        self.lock = Lock()
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        # Read and migrate once. Later appends and reads reuse this compact
        # in-memory state; the JSON file remains the durable snapshot.
        with self.lock:
            self._state = self._load_locked()
            self._save_locked()

    def _empty_events(self):
        return {
            bucket: {
                category: {}
                for category in self.CATEGORIES
            }
            for bucket in self.ACTIVITY_BUCKETS
        }

    def _empty_state(self):
        return {
            'events': self._empty_events(),
            'last_signatures': {}
        }

    def _clean_text(self, value, fallback=''):
        text = " ".join(str(value or '').replace('\r', ' ').replace('\n', ' ').split())
        return text or fallback

    def _timestamp(self, value):
        try:
            return float(value or 0)
        except Exception:
            return 0.0

    def _bucket_for_timestamp(self, timestamp, now=None):
        clean_timestamp = self._timestamp(timestamp)

        if clean_timestamp <= 0:
            return None

        current_time = self._timestamp(now) or time.time()
        bucket_index = int(
            max(0.0, current_time - clean_timestamp)
            // self.BUCKET_SECONDS
        )

        if bucket_index >= len(self.ACTIVITY_BUCKETS):
            return None

        return self.ACTIVITY_BUCKETS[bucket_index]

    def _stored_event_id(self, event, kind):
        timestamp = self._timestamp(event.get('ts'))
        device_id = self._clean_text(event.get('deviceID'))
        return f"activity_{int(timestamp * 1_000_000)}_{kind}_{device_id}"

    def _event_category(self, event):
        explicit = self._clean_text(event.get('category')).lower()
        source = self._clean_text(event.get('source')).lower()
        kind = self._clean_text(event.get('kind')).lower()
        signature = f'{source}:{kind}'

        if kind == 'security_route' or source == 'security-route':
            return 'security'

        if explicit in ('automation', 'system', 'users'):
            return explicit

        if any(token in signature for token in (
            'automation',
            'route',
            'schedule',
            'timer',
        )):
            return 'automation'

        if any(token in signature for token in (
            'user',
            'login',
            'logout',
            'dashboard',
            'button',
            'switch',
        )):
            return 'users'

        return 'system'

    def _packed_event_state(
        self,
        state,
        status='',
        detail='',
    ):
        clean_state = self._clean_text(
            state,
            'Activity',
        )
        clean_action = (
            self._clean_text(status)
            or self._clean_text(detail)
        )

        if (
            not clean_action
            or clean_action == clean_state
        ):
            return clean_state

        return (
            f'{clean_state} — '
            f'{clean_action}'
        )

    def _compact_event(self, event):
        if not isinstance(event, dict):
            return None

        device_id = self._clean_text(
            event.get('deviceID')
        )
        timestamp = self._timestamp(
            event.get('ts')
        )
        event_type = self._clean_text(
            event.get('type')
        ).lower()

        if event_type == 'event':
            state = self._packed_event_state(
                event.get('state'),
                event.get('status'),
                event.get('detail'),
            )
        else:
            state = self._clean_text(
                event.get('state')
                or event.get('status')
            )

        if (
            not device_id
            or timestamp <= 0
            or not state
        ):
            return None

        return {
            'deviceID': device_id,
            'ts': timestamp,
            'state': state,
        }

    def _client_and_child(self, device_id):
        client = self.clients.get(device_id)

        if isinstance(client, dict):
            return client, None

        parent_id, separator, child_id = str(device_id or '').partition(':child:')

        if not separator:
            return {}, None

        parent = self.clients.get(parent_id)

        if not isinstance(parent, dict):
            return {}, None

        children = parent.get('tapo_children')

        if not isinstance(children, list):
            return parent, None

        for index, child in enumerate(children):
            if not isinstance(child, dict):
                continue

            candidate_id = str(
                child.get('id')
                or child.get('device_id')
                or child.get('deviceId')
                or child.get('child_id')
                or child.get('childId')
                or child.get('position')
                or child.get('slot_number')
                or index + 1
            ).strip()

            if candidate_id == child_id:
                return parent, child

        return parent, None

    def _presentation_fields(self, event, category, kind):
        device_id = self._clean_text(
            event.get('deviceID')
        )
        packed_state = self._clean_text(
            event.get('state'),
            'Activity',
        )
        state, separator, detail = (
            packed_state.partition(' — ')
        )
        state = self._clean_text(
            state,
            'Activity',
        )
        detail = (
            self._clean_text(detail)
            if separator
            else ''
        )
        state_key = state.lower()
        client, child = self._client_and_child(
            device_id
        )

        name = self._clean_text(
            (child or {}).get('name')
            or (child or {}).get('alias')
            or (child or {}).get('display_name')
            or (child or {}).get('child_name')
            or client.get('clientName')
            or client.get('tapo_alias')
            or client.get('matter_node_label')
            or client.get('matter_product_name')
            or device_id,
            'Device'
        )
        zone = self._clean_text(
            client.get('zone_name')
            or client.get('zoneName')
            or client.get('room')
        )

        if kind in (
            'automation_route',
            'security_route',
        ):
            status = state
        elif (
            kind == 'tapo_recharge'
            and state_key in ('on', 'off')
        ):
            status = (
                'Charging started'
                if state_key == 'on'
                else 'Charging stopped'
            )
        elif kind == 'matter_contact' and state_key in (
            'open',
            'closed',
        ):
            status = (
                'Opened'
                if state_key == 'open'
                else 'Closed'
            )
        elif kind == 'matter_motion':
            status = 'Motion detected'
        elif kind == 'matter_button_press':
            status = 'Pressed'
        elif state_key == 'on':
            status = 'On'
        elif state_key == 'off':
            status = 'Off'
        else:
            status = state

        icon = 'history'
        accent = 'system'

        if kind == 'tapo_light_power':
            icon = 'emoji_objects'
            accent = 'yellow'
        elif kind in ('tapo_power', 'tapo_extender_child_power'):
            icon = 'power'
            accent = 'purple'
        elif kind == 'matter_contact':
            icon = 'sensor_door'
            accent = 'green' if state_key == 'open' else 'red'
        elif kind == 'matter_motion':
            icon = 'motion_sensor_active'
            accent = 'orange'
        elif kind == 'matter_switch_power':
            icon = 'toggle_on'
            accent = 'purple'
        elif kind == 'matter_button_press':
            icon = 'radio_button_checked'
            accent = 'gold'
        elif kind == 'tapo_recharge':
            icon = 'battery_charging_full'
            accent = (
                'green'
                if state_key == 'on'
                else 'purple'
            )
        elif kind == 'tapo_day_reset':
            icon = 'light_mode'
            accent = 'yellow'
        elif kind == 'security_route':
            icon = 'security'
            accent = 'orange'
        elif kind == 'automation_route':
            icon = 'auto_awesome'
            accent = 'purple'
        elif category == 'security':
            icon = 'security'
            accent = 'orange'
        elif category == 'automation':
            icon = 'auto_awesome'
            accent = 'purple'
        elif category == 'users':
            icon = 'group'
            accent = 'purple'

        if kind == 'tapo_recharge':
            source = 'automation:tapo-recharge'
        elif kind == 'tapo_day_reset':
            source = 'automation:tapo-day-reset'
        elif kind.startswith('tapo_'):
            source = 'tapo'
        elif kind.startswith('matter_'):
            source = 'matter'
        elif kind.endswith('_route'):
            source = f'{category}-route'
        else:
            source = 'device'

        return {
            'id': self._stored_event_id(event, kind),
            'ts': self._timestamp(event.get('ts')),
            'type': (
                'event'
                if (
                    kind.endswith('_route')
                    or kind in (
                        'tapo_recharge',
                        'tapo_day_reset',
                    )
                )
                else 'device_state'
            ),
            'source': source,
            'deviceID': device_id,
            'name': name,
            'zone': zone,
            'kind': kind,
            'icon': icon,
            'accent': accent,
            'status': status,
            'detail': detail,
            'state': state,
            'category': category,
        }

    def _stored_event_records(self, stored_events):
        if isinstance(stored_events, list):
            for event in stored_events:
                if isinstance(event, dict):
                    yield (
                        self._event_category(event),
                        self._clean_text(event.get('kind'), 'activity'),
                        event,
                    )
            return

        if not isinstance(stored_events, dict):
            return

        for bucket in self.ACTIVITY_BUCKETS:
            categories = stored_events.get(bucket)

            if not isinstance(categories, dict):
                continue

            for category in self.CATEGORIES:
                kinds = categories.get(category)

                if not isinstance(kinds, dict):
                    continue

                for kind, items in kinds.items():
                    clean_kind = self._clean_text(kind, 'activity')
                    clean_category = self._event_category({
                        'category': category,
                        'kind': clean_kind,
                    })

                    if not isinstance(items, list):
                        continue

                    for event in items:
                        if isinstance(event, dict):
                            yield clean_category, clean_kind, event

    def _group_events(self, stored_events, *, sort_items=False):
        grouped = self._empty_events()
        now = time.time()

        for category, kind, raw_event in self._stored_event_records(stored_events):
            event = self._compact_event(raw_event)

            if event is None:
                continue

            bucket = self._bucket_for_timestamp(event.get('ts'), now)

            if bucket is None:
                continue

            grouped[bucket][category].setdefault(
                kind,
                [],
            ).append(event)

        if sort_items:
            for categories in grouped.values():
                for kinds in categories.values():
                    for items in kinds.values():
                        items.sort(
                            key=lambda item: item['ts'],
                            reverse=True,
                        )

        return grouped

    def _load_locked(self):
        try:
            data = read_json_object(self.state_file)

            signatures = data.get('last_signatures')

            return {
                'events': self._group_events(
                    data.get('events'),
                    sort_items=True,
                ),
                'last_signatures': (
                    signatures
                    if isinstance(signatures, dict)
                    else {}
                ),
            }
        except JsonStateReadError:
            return self._empty_state()

    def _save_locked(self):
        self._state['events'] = self._group_events(
            self._state.get('events')
        )
        self._state['last_signatures'] = dict(
            self._state.get('last_signatures') or {}
        )

        write_json_atomic(self.state_file, self._state)

    def _append_event_locked(self, event, category, kind):
        bucket = self._bucket_for_timestamp(event.get('ts'))

        if bucket is None:
            return False

        self._state['events'][bucket][category].setdefault(
            kind,
            [],
        ).insert(0, event)

        return True

    def append(self, event):
        if not isinstance(event, dict):
            return None

        event_type = self._clean_text(event.get('type'), 'device_state')

        if event_type == 'event':
            return self.record_event(
                deviceID=event.get('deviceID'),
                name=event.get('name'),
                kind=event.get('kind') or 'event',
                state=event.get('state') or 'event',
                status=event.get('status'),
                icon=event.get('icon') or 'history',
                accent=event.get('accent') or 'system',
                source=event.get('source') or 'device',
                detail=event.get('detail') or '',
                category=event.get('category') or '',
            )

        if event_type != 'device_state':
            return None

        return self.record_state_change(
            deviceID=event.get('deviceID'),
            name=event.get('name'),
            kind=event.get('kind') or 'device',
            state=event.get('state'),
            status=event.get('status'),
            icon=event.get('icon') or 'history',
            accent=event.get('accent') or 'system',
            source=event.get('source') or 'device',
            detail=event.get('detail') or '',
            category=event.get('category') or '',
            record_initial=bool(event.get('record_initial'))
        )

    def record_state_change(self, *, deviceID, name, kind, state, status, icon, accent, source='device', detail='', category='', record_initial=False):
        clean_device_id = self._clean_text(deviceID)
        clean_kind = self._clean_text(kind, 'device')
        clean_state = self._clean_text(state)

        if not clean_device_id or not clean_state:
            return None

        clean_source = self._clean_text(source, 'device')
        clean_category = self._event_category({
            'category': category,
            'source': clean_source,
            'kind': clean_kind,
        })
        signature_key = f"device_state:{clean_source}:{clean_device_id}:{clean_kind}"
        signature = clean_state

        with self.lock:
            signatures = self._state.setdefault(
                'last_signatures',
                {},
            )
            previous = signatures.get(signature_key)

            if previous == signature:
                return None

            signatures[signature_key] = signature

            if previous is None and not record_initial:
                self._save_locked()
                return None

            item = {
                'deviceID': clean_device_id,
                'ts': time.time(),
                'state': clean_state,
            }

            self._append_event_locked(
                item,
                clean_category,
                clean_kind,
            )
            self._save_locked()

        return self._presentation_fields(
            item,
            clean_category,
            clean_kind,
        )
    
    def record_event(
        self,
        *,
        deviceID,
        name,
        kind,
        state,
        status,
        icon,
        accent,
        source='device',
        detail='',
        category='',
    ):
        clean_device_id = self._clean_text(
            deviceID
        )

        if not clean_device_id:
            return None

        clean_source = self._clean_text(
            source,
            'device',
        )
        clean_kind = self._clean_text(
            kind,
            'event',
        )
        clean_category = self._event_category({
            'category': category,
            'source': clean_source,
            'kind': clean_kind,
        })
        item = {
            'deviceID': clean_device_id,
            'ts': time.time(),
            'state': self._packed_event_state(
                state,
                status,
                detail,
            ),
        }

        with self.lock:
            self._append_event_locked(
                item,
                clean_category,
                clean_kind,
            )
            self._save_locked()

        return self._presentation_fields(
            item,
            clean_category,
            clean_kind,
        )

    def reset_state_signature(self, *, deviceID, kind, source='device'):
        clean_device_id = self._clean_text(deviceID)
        clean_kind = self._clean_text(kind, 'device')
        clean_source = self._clean_text(source, 'device')

        if not clean_device_id:
            return False

        signature_key = f"device_state:{clean_source}:{clean_device_id}:{clean_kind}"

        with self.lock:
            signatures = self._state.setdefault(
                'last_signatures',
                {},
            )

            if signature_key not in signatures:
                return False

            signatures.pop(signature_key, None)
            self._save_locked()

        return True
    
    def _event_stream(
        self,
        items,
        category,
        kind,
        oldest_cutoff,
        newest_cutoff,
        before_ts,
    ):
        for raw_item in items:
            item = self._compact_event(raw_item)

            if item is None:
                continue

            timestamp = item['ts']

            if timestamp < oldest_cutoff:
                break

            if (
                newest_cutoff and
                timestamp > newest_cutoff
            ):
                continue

            if before_ts and timestamp >= before_ts:
                continue

            yield timestamp, category, kind, item

    def recent_page(
        self,
        limit=20,
        age_text=None,
        from_hours=0,
        to_hours=0,
        category='all',
        before_ts=0,
    ):
        try:
            clean_limit = max(
                1,
                min(self.max_events, int(limit or 20)),
            )
        except Exception:
            clean_limit = 20

        try:
            clean_from_hours = max(
                0,
                min(
                    168,
                    float(from_hours or 0),
                ),
            )
        except Exception:
            clean_from_hours = 0

        try:
            clean_to_hours = max(
                0,
                min(
                    167,
                    float(to_hours or 0),
                ),
            )
        except Exception:
            clean_to_hours = 0

        if (
            clean_from_hours and
            clean_to_hours >= clean_from_hours
        ):
            clean_to_hours = max(
                0,
                clean_from_hours - 1,
            )

        clean_category = self._clean_text(
            category,
            'all',
        ).lower()

        if clean_category not in self.CATEGORIES:
            clean_category = 'all'

        clean_before_ts = self._timestamp(before_ts)
        now = time.time()
        retention_cutoff = (
            now
            - len(self.ACTIVITY_BUCKETS) * self.BUCKET_SECONDS
        )
        oldest_cutoff = max(
            retention_cutoff,
            (
                now - clean_from_hours * 3600
                if clean_from_hours
                else retention_cutoff
            ),
        )
        newest_cutoff = (
            now - clean_to_hours * 3600
            if clean_to_hours
            else 0
        )

        with self.lock:
            streams = []
            oldest_ts = 0.0

            for bucket in self.ACTIVITY_BUCKETS:
                categories = self._state['events'].get(
                    bucket,
                    {},
                )

                for event_category in self.CATEGORIES:
                    kinds = categories.get(
                        event_category,
                        {},
                    )

                    if not isinstance(kinds, dict):
                        continue

                    for kind, items in kinds.items():
                        if not isinstance(items, list):
                            continue

                        for raw_item in reversed(items):
                            timestamp = self._timestamp(
                                raw_item.get('ts')
                            )

                            if timestamp >= retention_cutoff:
                                oldest_ts = (
                                    timestamp
                                    if not oldest_ts
                                    else min(oldest_ts, timestamp)
                                )
                                break

                        if clean_category in (
                            'all',
                            event_category,
                        ):
                            streams.append(
                                self._event_stream(
                                    items,
                                    event_category,
                                    kind,
                                    oldest_cutoff,
                                    newest_cutoff,
                                    clean_before_ts,
                                )
                            )

            merged = heapq.merge(
                *streams,
                key=lambda record: record[0],
                reverse=True,
            )
            records = []

            for record in merged:
                records.append(record)

                if len(records) > clean_limit:
                    break

            has_more = len(records) > clean_limit
            events = [
                self._presentation_fields(
                    item,
                    event_category,
                    kind,
                )
                for _, event_category, kind, item
                in records[:clean_limit]
            ]

        for item in events:
            item['time'] = (
                age_text(item.get('ts'))
                if callable(age_text)
                else ''
            )

        return {
            'items': events,
            'has_more': has_more,
            'oldest_ts': oldest_ts,
        }

    def recent(
        self,
        limit=20,
        age_text=None,
        hours=24,
        category='all',
    ):
        return self.recent_page(
            limit=limit,
            age_text=age_text,
            from_hours=hours,
            to_hours=0,
            category=category,
        )['items']