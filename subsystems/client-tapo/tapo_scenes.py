"""Homepage Scene transport and asynchronous fan-out.

Input: normalized commands grouped by physical device, captured route identity.
Output: one truthful result per device. Explicit session rejection renews authentication.
"""
import asyncio
import time
from typing import Any

from . import tapo_control as control


async def _scene_write(item, dev, operation):
    """Renew only an explicitly expired SDK session; never replay ambiguous I/O."""
    async def send():
        return await control._tapo_wait(
            operation(), control.TAPO_DEVICE_CALL_TIMEOUT_SECONDS, 'Tapo Scene write')

    try:
        return await send()
    except Exception as error:
        # tapo 0.9.0 exposes Rust errors as plain Python Exceptions containing
        # Debug text, not typed errors. Match only its explicit expiry variants.
        if not str(error).startswith((
            'Tapo(Unauthorized { kind: "SESSION_TIMEOUT",',
            'Tapo(Unauthorized { kind: "SESSION_EXPIRED",',
        )):
            raise
    try:
        await control._tapo_wait(dev.refresh_session(),
                                 control.TAPO_DEVICE_CALL_TIMEOUT_SECONDS,
                                 'Tapo Scene authentication renewal')
        return await send()
    except BaseException:
        # Do not strand the next click with a session whose renewal failed.
        if control._tapo_handles.get(item['id']) is dev:
            control._tapo_handles.pop(item['id'], None)
        raise


async def set_tapo_scene_from_info(item: dict[str, Any], commands: list[dict]) -> dict[str, Any]:
    """Send final Scene state without probes; renew explicitly expired sessions.

    The caller owns this device's command slot. Other devices may authenticate
    and send concurrently; only this device's existing session is reused.
    """
    item = {**control._tapo_devices.get(item.get('id'), {}), **item}
    device_id = item.get('id')
    if not device_id or not item.get('ip'):
        raise ValueError('Missing Tapo device identity or host')
    kind = str(item.get('kind') or '').lower()
    if kind not in {'bulb', 'lightstrip', 'plug', 'outlet_extender', 'hub'}:
        raise ValueError('Device does not support Scene commands')
    power = None
    brightness = None
    color = None
    color_temperature = None
    children = []
    for command in commands:
        action, value = command.get('action'), command.get('value')
        if action in {'child_on', 'child_off'}:
            children.append(command)
        elif action in {'on', 'off'}:
            power = action == 'on'
        elif action in {'brightness', 'brightness_no_power'}:
            brightness = int(value)
            if not 1 <= brightness <= 100:
                raise ValueError('brightness must be 1-100')
            if action == 'brightness':
                power = True
        elif action in {'color', 'color_no_power'}:
            if not isinstance(value, dict):
                raise ValueError('color requires hue and saturation')
            color = (int(value.get('hue', 0)), int(value.get('saturation', 100)))
            if not 0 <= color[0] <= 360 or not 0 <= color[1] <= 100:
                raise ValueError('Invalid hue or saturation')
            color_temperature = None
            if action == 'color':
                power = True
        elif action in {'color_temperature', 'color_temperature_no_power'}:
            color_temperature = int(value)
            if not 2500 <= color_temperature <= 6500:
                raise ValueError('color temperature must be 2500-6500')
            color = None
            if action == 'color_temperature':
                power = True
        else:
            raise ValueError(f'Unsupported Scene action: {action}')
    if children:
        if kind not in {'outlet_extender', 'hub'}:
            raise ValueError('Device does not support child Scene commands')
        if len(children) != len(commands):
            raise ValueError('Cannot mix child and parent Scene commands')
        # Extender child switching uses its established transport. Each child
        # is an independent outlet; never redirect a child command to its parent.
        for command in children:
            result = await control.set_tapo_device_from_info(
                item, command['action'], command.get('value'), fast=True)
            item = result['device']
        return {'ok': True, 'id': device_id, 'device': item}
    if not commands:
        raise ValueError('Empty Scene target')
    if kind == 'outlet_extender':
        raise ValueError('Outlet extenders require a child_id')
    dev = await control._get_tapo_device(item, verify_cached=False, single_attempt=True)
    builder_factory = getattr(dev, 'set', None)
    has_light_value = brightness is not None or color is not None or color_temperature is not None
    final_power = power if power is not None else item.get('is_on') is not False
    if kind in {'bulb', 'lightstrip'} and callable(builder_factory):
        builder = builder_factory()
        if brightness is not None:
            builder = builder.brightness(brightness)
        if color is not None:
            builder = builder.hue_saturation(*color)
        elif color_temperature is not None:
            builder = builder.color_temperature(color_temperature)
        builder = builder.on() if final_power else builder.off()
        await _scene_write(item, dev, lambda: builder.send(dev))
    elif not has_light_value:
        if power is None:
            raise ValueError('Missing Scene power state')
        await _scene_write(item, dev, lambda: dev.on() if power else dev.off())
    else:
        # The pinned SDK exposes no combined builder for dimmable-only bulbs.
        # Preserve their supported power semantics using the minimum available
        # methods, with no verification reads or application retry loops.
        if color is not None or color_temperature is not None:
            raise ValueError('Device SDK does not support the requested combined light state')
        if power is True and item.get('is_on') is not True:
            await _scene_write(item, dev, dev.on)
        await _scene_write(item, dev, lambda: dev.set_brightness(brightness))
        if not final_power:
            await _scene_write(item, dev, dev.off)
    item.update(control_ready=True, control_error='', is_on=final_power,
                last_command_at=time.time())
    if brightness is not None:
        item['brightness'] = brightness
    if color is not None:
        item.update(hue=color[0], saturation=color[1], color_temperature=0)
    elif color_temperature is not None:
        item['color_temperature'] = color_temperature
    control._tapo_devices[device_id] = item
    return {'ok': True, 'id': device_id, 'device': item}


async def dispatch_scene(targets, prepare, reconcile, send):
    """Dispatch all independent targets; only a target's own slot may wait."""
    timings = []

    async def send_target(target):
        device_id = target['deviceID']
        acquired_at = None
        try:
            async with target['slot']:
                acquired_at = time.monotonic()
                item = prepare(target)
                result = await send(item, target['commands'])
                client = reconcile(target, result)
                return dict(deviceID=device_id, ok=True, device=result.get('device', {}), client=client)
        except Exception as error:
            return dict(deviceID=device_id, ok=False, error=str(error))
        finally:
            ended = time.monotonic()
            timings.append(((acquired_at if acquired_at is not None else ended) - target['reservedAt'],
                            ended - acquired_at if acquired_at is not None else 0.0))

    try:
        results = await asyncio.gather(*(send_target(target) for target in targets))
        return results, timings
    finally:
        for target in targets:
            target['slot'].cancel()
