import unittest
from unittest.mock import patch

from realme_buds.bluez import Device
from realme_buds.profiles import PROFILES
from realme_buds.protocol import NOTIFY_STATE, QUERY_BROADCAST_CODES, SUBSCRIBE_BROADCAST, Frame
from realme_buds.session import OpoSession


DEVICE = Device(
    address="AA:BB:CC:DD:EE:FF",
    name="OnePlus Buds Pro 2",
    connected=True,
    uuids=("0000079a-d102-11e1-9b23-00025b00a5a5",),
    battery=80,
)


class SessionTests(unittest.TestCase):
    def test_session_subscribes_and_redacts_notification_payloads(self):
        peer_payload = b"\x06private peer device name and address"
        transport = FakeTransport(
            {
                QUERY_BROADCAST_CODES: [Frame(0x8200, 1, b"\x00\x02\x04\x06")],
                SUBSCRIBE_BROADCAST: [Frame(NOTIFY_STATE, 0xFF, peer_payload)],
            }
        )
        with patch("realme_buds.session.RfcommTransport", return_value=transport):
            with OpoSession(DEVICE, PROFILES["062014"]) as session:
                batch = session.authenticate_and_subscribe()
                self.assertEqual(session.advertised_event_codes, (4, 6))
        self.assertEqual(batch.events[-1].kind, "notification")
        self.assertEqual(batch.events[-1].data, {"event_code": 6})
        self.assertNotIn("private peer", repr(batch))
        self.assertIn((SUBSCRIBE_BROADCAST, b"\x02\x04\x06"), transport.queries)

    def test_poll_returns_typed_safe_events_and_ignored_count(self):
        transport = FakeTransport({}, received=[
            Frame(0x8106, 1, b"\x01\x64\x02\x63"),
            Frame(0x9999, 2, b"secret"),
        ])
        with patch("realme_buds.session.RfcommTransport", return_value=transport):
            with OpoSession(DEVICE, PROFILES["062014"]) as session:
                batch = session.poll()
        self.assertEqual(batch.events[0].kind, "battery")
        self.assertEqual(batch.events[0].data["left"]["percentage"], 100)
        self.assertEqual(batch.ignored_frames, 1)
        self.assertNotIn("secret", repr(batch))

    def test_poll_queries_battery_periodically_and_on_demand(self):
        transport = FakeTransport({})
        with patch("realme_buds.session.RfcommTransport", return_value=transport):
            with OpoSession(DEVICE, PROFILES["062014"], battery_poll_interval=10.0) as session:
                # Initially not due
                session.poll()
                self.assertNotIn((0x0106, b""), transport.sent_queries)
                # On demand request
                session.request_battery()
                session.poll()
                self.assertIn((0x0106, b""), transport.sent_queries)

    def test_query_battery_returns_parsed_result(self):
        transport = FakeTransport({0x0106: [Frame(0x8106, 1, b"\x01\x50\x02\x50")]})
        with patch("realme_buds.session.RfcommTransport", return_value=transport):
            with OpoSession(DEVICE, PROFILES["062014"]) as session:
                result = session.query_battery()
                self.assertEqual(result["left"]["percentage"], 80)
                self.assertEqual(result["right"]["percentage"], 80)

    def test_session_must_be_connected(self):
        session = OpoSession(DEVICE, PROFILES["062014"])
        with self.assertRaisesRegex(RuntimeError, "not connected"):
            session.poll()

    def test_query_feature_switches(self):
        transport = FakeTransport({
            0x010D: [Frame(0x810D, 0, bytes.fromhex("00 02 04 01 28 01"))]
        })
        with patch("realme_buds.session.RfcommTransport", return_value=transport):
            with OpoSession(DEVICE, PROFILES["062014"]) as session:
                switches = session.query_feature_switches()
                self.assertEqual(switches, {"wear_detection": True, "game_mode": True})

    def test_set_feature_switch(self):
        transport = FakeTransport({
            0x0403: [Frame(0x8403, 1, b"\x00")]
        })
        with patch("realme_buds.session.RfcommTransport", return_value=transport):
            with OpoSession(DEVICE, PROFILES["062014"]) as session:
                session._authenticated = True
                success, batch = session.set_feature_switch("game_mode", True)
                self.assertTrue(success)
                self.assertEqual(batch.events[-1].kind, "feature_switches")
                self.assertEqual(batch.events[-1].data, {"game_mode": True})
                self.assertIn((0x0403, b"\x28\x01"), transport.queries)



class FakeTransport:
    def __init__(self, responses, received=None):
        self.responses = responses
        self.received = received or []
        self.queries = []
        self.sent_queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def query(self, command, *args, **_kwargs):
        payload = args[0] if args else b""
        self.queries.append((command, payload))
        return self.responses.get(command, [])

    def send_query(self, command, payload=b""):
        self.sent_queries.append((command, payload))
        return 1

    def request(self, command, payload, response_command, on_frames=None, **kwargs):
        self.queries.append((command, payload))
        frames = self.responses.get(command, [])
        return frames[0] if frames else Frame(response_command, 1, b"")

    def exchange_raw(self, *_args, **_kwargs):
        return []

    def receive(self, _wait):
        return self.received


if __name__ == "__main__":
    unittest.main()
