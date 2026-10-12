"""Pinned SDK contracts with controlled transports; no devices or credentials."""
import asyncio
import importlib.metadata
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tests.devices.tapo.test_tapo_command_integrity import load_tapo_control


class PinnedSdkTests(unittest.TestCase):
    def test_color_bulb_and_strip_builder_api_matches_pinned_binding(self):
        import tapo
        from tapo.requests import LightSetDeviceInfoParams
        self.assertEqual(importlib.metadata.version('tapo'), '0.9.0')
        for handler in (tapo.ColorLightHandler, tapo.RgbLightStripHandler, tapo.RgbicLightStripHandler):
            self.assertTrue(callable(handler.set))
        for name in ('on', 'off', 'brightness', 'hue_saturation', 'color_temperature', 'send'):
            self.assertTrue(callable(getattr(LightSetDeviceInfoParams, name)))
        self.assertFalse(hasattr(tapo.LightHandler, 'set'))

    def test_dimmable_write_uses_discovered_config_one_query_no_replay_and_closes(self):
        from kasa.device_factory import get_protocol
        control = load_tapo_control()
        protocol = SimpleNamespace(query=AsyncMock(return_value={}), close=AsyncMock())
        item = dict(id='dim', ip='192.0.2.1', model='L510', device_type='SMART.TAPOBULB',
                    encrypt_type='KLAP', login_version='2', http_port='80')
        with patch('kasa.device_factory.get_protocol', return_value=protocol) as factory:
            power = asyncio.run(control._set_tapo_dimmable_state(item, 28, False))
        self.assertFalse(power)
        protocol.query.assert_awaited_once_with(
            {'set_device_info': {'device_on': False, 'brightness': 28}}, retry_count=0)
        protocol.close.assert_awaited_once()
        config = factory.call_args.args[0]
        self.assertEqual((config.host, config.connection_type.encryption_type.value,
                          config.connection_type.login_version), ('192.0.2.1', 'KLAP', 2))
        self.assertTrue(factory.call_args.kwargs['strict'])

    def test_dimmable_failure_closes_without_replay_or_guessing(self):
        control = load_tapo_control()
        protocol = SimpleNamespace(query=AsyncMock(side_effect=TimeoutError('ambiguous I/O')),
                                   close=AsyncMock())
        item = dict(ip='192.0.2.1', device_type='SMART.TAPOBULB', encrypt_type='AES', login_version='2')
        with patch('kasa.device_factory.get_protocol', return_value=protocol):
            with self.assertRaises(TimeoutError):
                asyncio.run(control._set_tapo_dimmable_state(item, 28, True))
        protocol.query.assert_awaited_once()
        protocol.close.assert_awaited_once()
        with patch('kasa.device_factory.get_protocol') as factory, self.assertRaisesRegex(ValueError, 'metadata'):
            asyncio.run(control._set_tapo_dimmable_state({'ip': '192.0.2.1'}, 28, True))
        factory.assert_not_called()

    def test_real_kasa_protocol_emits_one_combined_smart_request(self):
        from kasa import Credentials, DeviceConfig
        from kasa.protocols import SmartProtocol
        import json
        sent = []
        class Transport:
            _host = '192.0.2.1'
            _config = DeviceConfig(host=_host, credentials=Credentials('fixture', 'fixture'))
            _credentials = _config.credentials
            async def send(self, request):
                sent.append(json.loads(request))
                return {'error_code': 0}
            async def close(self): pass
        async def send():
            protocol = SmartProtocol(transport=Transport())
            try:
                await protocol.query({'set_device_info': {'device_on': True, 'brightness': 28}}, retry_count=0)
            finally:
                await protocol.close()
        asyncio.run(send())
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]['method'], 'set_device_info')
        self.assertEqual(sent[0]['params'], {'device_on': True, 'brightness': 28})
