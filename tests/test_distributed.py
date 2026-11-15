"""Two-device planning, strict control protocol, real TLS/backpressure and Qt lifecycle."""
import ipaddress
import math
import os
import socket
import threading
import time
import unittest
from unittest.mock import patch

from nexus_ui.compute_plan import devices, plan_layers, validate_profile


def profile(speed=20, free=20000, device='MTL0'):
    return dict(device=device, name='Test GPU', free=free, total=24000, tps=speed)


class PlanningTests(unittest.TestCase):
    def test_faster_gpu_gets_more_layers_and_memory_caps_allocation(self):
        slow, fast = profile(10), profile(40, device='CUDA0')
        plan = plan_layers(slow, fast, size=4 * 1024**3, layers=33, embedding=4096, context=1024)
        self.assertGreater(plan.remote_layers, plan.local_layers)
        self.assertEqual(plan.local_layers + plan.remote_layers, 33)
        fast['free'] = 3500
        capped = plan_layers(slow, fast, size=4 * 1024**3, layers=33, embedding=4096, context=1024)
        self.assertLess(capped.remote_layers, plan.remote_layers)
        self.assertGreaterEqual(capped.remote_layers, 2)

    def test_unknown_performance_is_labelled_and_oom_rejected(self):
        plan = plan_layers(profile(0), profile(50), size=4 * 1024**3, layers=33, embedding=4096, context=1024)
        self.assertIn('ungemessen', plan.basis)
        with self.assertRaises(ValueError):
            plan_layers(profile(free=2048), profile(free=2048), size=10 * 1024**3, layers=33, embedding=4096, context=16384)
        for speed in (math.nan, math.inf, -1, True):
            with self.assertRaises(ValueError):
                validate_profile(profile(speed))

    def test_upstream_device_names(self):
        found = devices('MTL0: Apple M5 (24000 MiB, 20000 MiB free)\nRPC0: remote (16000 MiB, 15000 MiB free)\n')
        self.assertEqual([p['device'] for p in found], ['MTL0', 'RPC0'])


os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtCore import QObject, Signal, QTimer
    from PySide6.QtTest import QTest
    from nexus_ui.app import make_application
    from nexus_ui.compute_tunnel import Tunnel
    from nexus_ui.pairing_transport import validate_message, read_invitation, make_invitation
    from nexus_ui.compute_protocol import REVISION
    from nexus_ui.distributed import DistributedSession
    from test_local_model import FixtureRunner
except ModuleNotFoundError as exc:
    if exc.name != 'PySide6':
        raise
    Tunnel = None

if Tunnel:
    class FakePairing(QObject):
        compute_message = Signal(dict)
        state_changed = Signal()

        def __init__(self):
            super().__init__()
            self.connected = True
            self.local_model = {'type': 'model', 'state': 'ready', 'sha256': 'a' * 64,
                                'name': 'test.gguf', 'size': 4000000, 'parts': 1}
            self.peer_model = dict(self.local_model)
            self.thread = self
            self.local_address = self.peer_address = '127.0.0.1'
            self.sent = []

        def send(self, message):
            self.sent.append(message)


@unittest.skipIf(Tunnel is None, 'Install requirements-ui.txt')
class ComputeQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        make_application()

    def wait(self, condition, seconds=10):
        deadline = time.monotonic() + seconds
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(10)
            time.sleep(.005)
        self.assertTrue(condition())

    def test_control_protocol_rejects_unknown_fields_and_revision(self):
        with patch('nexus_ui.pairing_transport.lan_address', side_effect=ipaddress.IPv4Address):
            code = make_invitation('127.0.0.1', 1234, b'a' * 32, b'b' * 32)
            message = dict(type='compute', action='ready', profile=profile(), code=code,
                           sha256='a' * 64, revision=REVISION)
            validate_message(message)
            for addition in ({'path': '/private/model.gguf'}, {'revision': 'old'}, {'sha256': 'bad'}):
                with self.assertRaises(ValueError):
                    validate_message({**message, **addition})
        with self.assertRaises(ValueError):
            validate_message(dict(type='compute', action='request', id='shell'))

    def test_reservation_prevents_simultaneous_runs_and_releases_on_disconnect(self):
        runner, pairing = FixtureRunner(), FakePairing()
        cluster = DistributedSession(runner, pairing)
        cluster.enabled = True
        cluster.digest = 'a' * 64
        cluster.profile = profile()
        cluster.peer = dict(profile=profile())
        class Server:
            allowed = threading.Event()
            def allow(self): self.allowed.set()
            def revoke(self): self.allowed.clear()
        cluster.server = Server()
        cluster.receive(dict(action='request', id='b' * 32))
        self.assertTrue(runner.external_busy)
        self.assertTrue(cluster.server.allowed.is_set())
        self.assertEqual(pairing.sent[-1]['action'], 'accepted')
        self.assertFalse(runner.start('Must not run solo while reserved'))
        cluster.receive(dict(action='request', id='c' * 32))
        self.assertEqual(pairing.sent[-1]['action'], 'rejected')
        pairing.connected = False
        cluster.check_state()
        self.assertFalse(runner.external_busy)
        self.assertIsNone(cluster.reservation)
        self.assertIsNone(cluster.peer)

    def test_assignment_requires_repeating_layers_on_both_gpus(self):
        runner = FixtureRunner()
        runner.distributed = dict(layers=4, local=profile(), remote_device='RPC0', plan=True)
        runner.assignment = {0: 'MTL0', 1: 'MTL0', 2: 'MTL0', 3: 'RPC0'}
        self.assertFalse(runner.assignment_valid())
        runner.assignment[2] = 'RPC0'
        self.assertTrue(runner.assignment_valid())
        runner.assignment[0] = 'CPU'
        self.assertFalse(runner.assignment_valid())

    def test_windows_benchmark_and_single_completion_notification(self):
        runner, pairing = FixtureRunner(), FakePairing()
        cluster = DistributedSession(runner, pairing)
        cluster.enabled = True
        cluster.profile = profile(0)
        with patch.object(cluster, 'start_worker'):
            cluster.bench_finished(0, 'GPU diagnostic\r\n[\r\n {"avg_ts": 75.5}\r\n]\r\n')
        self.assertEqual(cluster.profile['tps'], 75.5)
        cluster.pending = 'b' * 32
        cluster.launched = True
        notifications = []
        runner.finished.connect(notifications.append)
        cluster.run_finished('completed')
        self.assertEqual(notifications, [])
        self.assertIsNone(cluster.pending)

    def test_rpc_registered_before_device_selection(self):
        from nexus_ui.compute_plan import Plan
        runner = FixtureRunner()
        runner.distributed = dict(endpoint='127.0.0.1:1234', local=profile(), remote_device='RPC0',
                                  plan=Plan(10, 17, 'test'))
        _, args = runner._runtime_command()
        self.assertLess(args.index('--rpc'), args.index('--device'))
        self.assertEqual(args[args.index('--device') + 1], 'MTL0,RPC0')
        self.assertEqual(args[args.index('--fit') + 1], 'off')
        self.assertEqual(args[args.index('--tensor-split') + 1], '10,17')

    def test_real_pinned_tls_transfers_large_bidirectional_payload_and_stops(self):
        stop = threading.Event()
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        listener.settimeout(.2)
        def echo():
            while not stop.is_set():
                try:
                    conn, _ = listener.accept()
                except TimeoutError:
                    continue
                with conn:
                    conn.settimeout(.2)
                    while not stop.is_set():
                        try:
                            data = conn.recv(65536)
                        except TimeoutError:
                            continue
                        if not data:
                            break
                        conn.sendall(data)
        echo_thread = threading.Thread(target=echo, daemon=True)
        echo_thread.start()
        tunnels = []
        try:
            with patch('nexus_ui.pairing_transport.lan_address', side_effect=ipaddress.IPv4Address):
                server = Tunnel(address='127.0.0.1', peer='127.0.0.1', worker_port=listener.getsockname()[1])
                tunnels.append(server)
                codes = []
                server.ready.connect(codes.append)
                server.allowed.set()
                server.start()
                self.wait(lambda: bool(codes))
                proxy = Tunnel(address='127.0.0.1', peer='127.0.0.1', invitation=codes[0])
                tunnels.append(proxy)
                ports = []
                proxy.ready.connect(ports.append)
                proxy.start()
                self.wait(lambda: bool(ports))
                result = []
                def transfer():
                    data = bytes(range(256)) * 20000
                    with socket.create_connection(('127.0.0.1', int(ports[0])), timeout=10) as client:
                        sender = threading.Thread(target=lambda: client.sendall(data))
                        sender.start()
                        received = bytearray()
                        while len(received) < len(data):
                            chunk = client.recv(65536)
                            if not chunk:
                                break
                            received.extend(chunk)
                        sender.join(timeout=10)
                        result.append(bytes(received) == data)
                thread = threading.Thread(target=transfer, daemon=True)
                thread.start()
                try:
                    self.wait(lambda: bool(result), seconds=15)
                except AssertionError:
                    self.fail(f'TLS byte counts: {server.transferred}, {proxy.transferred}')
                self.assertEqual(result, [True])
                address, port, fingerprint, secret = read_invitation(codes[0])
                # Neither a wrong certificate pin nor a wrong session secret
                # may reach the loopback worker, even from the paired address.
                for bad_pin, bad_secret in ((b'z' * 32, secret), (fingerprint, b'z' * 32)):
                    rejected = Tunnel(address='127.0.0.1', peer='127.0.0.1',
                                      invitation=make_invitation(address, port, bad_pin, bad_secret))
                    tunnels.append(rejected)
                    endpoints = []
                    rejected.ready.connect(endpoints.append)
                    rejected.start()
                    self.wait(lambda: bool(endpoints))
                    with socket.create_connection(('127.0.0.1', int(endpoints[0])), timeout=3) as client:
                        try:
                            client.sendall(b'not authorized')
                            self.assertEqual(client.recv(32), b'')
                        except ConnectionResetError:
                            pass
                server.allowed.clear()
        finally:
            for tunnel in tunnels:
                tunnel.stop()
            for tunnel in tunnels:
                self.wait(lambda t=tunnel: not t.isRunning())
            stop.set()
            echo_thread.join(timeout=2)
            listener.close()
