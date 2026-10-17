import unittest
from unittest.mock import Mock, patch

from realme_buds.transport import DEFAULT_CHANNELS, RfcommTransport, Transport, create_transport


class TransportTests(unittest.TestCase):
    def test_rfcomm_transport_implements_transport_protocol(self):
        transport = RfcommTransport("AA:BB:CC:DD:EE:FF")
        self.assertIsInstance(transport, Transport)
        self.assertFalse(transport.is_connected)

    @patch("realme_buds.transport.socket.socket")
    def test_is_connected_reflects_socket_lifecycle(self, socket_factory):
        sock = Mock()
        socket_factory.return_value = sock
        transport = RfcommTransport("AA:BB:CC:DD:EE:FF")
        self.assertFalse(transport.is_connected)
        with transport:
            self.assertTrue(transport.is_connected)
        self.assertFalse(transport.is_connected)

    def test_create_transport_factory(self):
        t1 = create_transport("AA:BB:CC:DD:EE:FF")
        self.assertIsInstance(t1, RfcommTransport)
        self.assertEqual(t1.address, "AA:BB:CC:DD:EE:FF")
        self.assertEqual(t1.candidate_channels, DEFAULT_CHANNELS)

        t2 = create_transport("AA:BB:CC:DD:EE:FF", channel=1, timeout=5.0)
        self.assertIsInstance(t2, RfcommTransport)
        self.assertEqual(t2.candidate_channels, (1,))
        self.assertEqual(t2.timeout, 5.0)

        with self.assertRaises(ValueError):
            create_transport("AA:BB:CC:DD:EE:FF", transport_type="unsupported")

    @patch("realme_buds.transport.time.sleep")
    @patch("realme_buds.transport.socket.socket")
    def test_retries_transient_busy(self, socket_factory, sleep):
        sockets = [Mock(), Mock(), Mock()]
        sockets[0].connect.side_effect = OSError(16, "busy")
        sockets[1].connect.side_effect = OSError(16, "busy")
        socket_factory.side_effect = sockets

        with RfcommTransport("AA:BB:CC:DD:EE:FF", connect_attempts=3, retry_delay=0.25):
            pass

        self.assertEqual(socket_factory.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        sockets[0].close.assert_called_once()
        sockets[1].close.assert_called_once()
        sockets[2].close.assert_called_once()

    @patch("realme_buds.transport.time.sleep")
    @patch("realme_buds.transport.socket.socket")
    def test_does_not_retry_non_busy_error(self, socket_factory, sleep):
        sock = Mock()
        sock.connect.side_effect = OSError(13, "denied")
        socket_factory.return_value = sock
        with self.assertRaises(OSError):
            with RfcommTransport("AA:BB:CC:DD:EE:FF", connect_attempts=3):
                pass
        self.assertEqual(socket_factory.call_count, 1)
        sleep.assert_not_called()
    @patch("realme_buds.transport.time.sleep")
    @patch("realme_buds.transport.socket.socket")
    def test_falls_back_to_next_candidate_channel_on_refused(self, socket_factory, sleep):
        sock_refused = Mock()
        sock_refused.connect.side_effect = OSError(111, "Connection refused")
        sock_success = Mock()
        socket_factory.side_effect = [sock_refused, sock_success]

        transport = RfcommTransport("AA:BB:CC:DD:EE:FF", channel=(15, 1))
        with transport:
            pass

        self.assertEqual(transport.channel, 1)
        self.assertEqual(socket_factory.call_count, 2)
        sock_refused.connect.assert_called_with(("AA:BB:CC:DD:EE:FF", 15))
        sock_success.connect.assert_called_with(("AA:BB:CC:DD:EE:FF", 1))
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
