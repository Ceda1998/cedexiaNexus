import socket
import time
import unittest

from scripts import benchmark_lan as lan


class LanBenchmarkTests(unittest.TestCase):
    def test_ping_summary_keeps_loss_and_uses_nearest_rank_p95(self):
        result = lan.summarize_ping(list(range(1, 20)))
        self.assertEqual(result["loss_percent"], 5.0)
        self.assertEqual(result["median_ms"], 10)
        self.assertEqual(result["p95_ms"], 19)
        self.assertIsNone(lan.summarize_ping([])["median_ms"])

    def test_transfer_protocol_both_directions(self):
        payload = b"test block"
        client, mac = socket.socketpair()
        with client, mac:
            deadline = time.monotonic() + 5
            client.sendall(b"U" + payload)
            lan.serve_transfer(mac, len(payload), payload, deadline)
            self.assertEqual(lan.receive(client, 1, deadline), b"K")
            client.sendall(b"D")
            lan.serve_transfer(mac, len(payload), payload, deadline)
            with client.makefile("rb") as stream:
                self.assertEqual(stream.read(len(payload)), payload)

    def test_incomplete_upload_fails_without_acknowledgement(self):
        client, mac = socket.socketpair()
        with client, mac:
            client.sendall(b"Ushort")
            client.shutdown(socket.SHUT_WR)
            with self.assertRaises(ConnectionError):
                lan.serve_transfer(mac, 64, b"unused", time.monotonic() + 5)

    def test_peer_arguments_accept_only_private_ipv4(self):
        from argparse import ArgumentTypeError

        self.assertEqual(lan.lan_address("192.168.1.42"), "192.168.1.42")
        for value in ("0.0.0.0", "127.0.0.1", "203.0.113.4", "example.test"):
            with self.subTest(value=value), self.assertRaises(ArgumentTypeError):
                lan.lan_address(value)
