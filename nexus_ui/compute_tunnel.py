"""Ephemeral, pinned TLS bridge to a loopback-only experimental RPC worker.

No RPC payload is parsed here. At most eight bounded streams per paired peer.
The session controller owns cancellation and the worker process.
"""
import hmac
import secrets
import select
import socket
from threading import Event, Thread, BoundedSemaphore
import time

from cryptography.hazmat.primitives import hashes
from OpenSSL import SSL
from PySide6.QtCore import QThread, Signal

from .pairing_transport import Channel, host_context, tls_context, make_invitation, read_invitation, PEER_ERRORS


class Tunnel(QThread):
    ready = Signal(str)
    failed = Signal()

    def __init__(self, *, address=None, peer=None, worker_port=None, invitation=None, parent=None):
        super().__init__(parent)
        self.address, self.peer = address, peer
        self.worker_port, self.invitation = worker_port, invitation
        self.cancelled = Event()
        self.allowed = Event()  # Worker is reachable only while a peer run is reserved.
        self.epoch = 0
        self.slots = BoundedSemaphore(8)
        self.children = []
        self.transferred = [0, 0]

    def stop(self):
        self.revoke()
        self.cancelled.set()

    def allow(self):
        self.epoch += 1
        self.allowed.set()

    def revoke(self):
        self.epoch += 1
        self.allowed.clear()

    def run(self):
        try:
            self.serve()
        except PEER_ERRORS:
            if not self.cancelled.is_set():
                self.failed.emit()
        finally:
            self.cancelled.set()
            for child in self.children:
                child.join(timeout=10)

    def serve(self):
        serving = self.invitation is None
        if serving:
            context, fingerprint = host_context()
            secret = secrets.token_bytes(32)
        else:
            target, port, fingerprint, secret = read_invitation(self.invitation)
            if target != self.peer:
                raise ValueError('Tunnel destination is not the paired peer')
            context = tls_context(False)
        with socket.socket() as listener:
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            listener.bind((self.address if serving else '127.0.0.1', 0))
            listener.listen(8)
            listener.settimeout(.2)
            own_port = listener.getsockname()[1]
            self.ready.emit(make_invitation(self.address, own_port, fingerprint, secret) if serving else str(own_port))
            while not self.cancelled.is_set():
                try:
                    raw, source = listener.accept()
                except TimeoutError:
                    continue
                if (serving and (source[0] != self.peer or not self.allowed.is_set())) or not self.slots.acquire(False):
                    raw.close()
                    continue
                args = (raw, serving, context, fingerprint, secret, None if serving else (target, port), self.epoch)
                child = Thread(target=self.connect_stream, args=args, daemon=True)
                self.children = [item for item in self.children if item.is_alive()]
                self.children.append(child)
                child.start()

    def connect_stream(self, raw, serving, context, fingerprint, secret, target, epoch):
        try:
            with raw:
                raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                if serving:
                    channel = Channel(context, raw, True, self.cancelled)
                    deadline = time.monotonic() + 8
                    channel.call(channel.tls.do_handshake, deadline)
                    proof = channel.receive(deadline)
                    if (not isinstance(proof, str) or not hmac.compare_digest(proof, secret.hex())
                            or not self.allowed.is_set() or epoch != self.epoch):
                        return
                    channel.send('accepted', deadline)
                    with socket.create_connection(('127.0.0.1', self.worker_port), timeout=5) as plain:
                        self.bridge(channel, plain, serving, epoch)
                else:
                    with socket.create_connection(target, timeout=5, source_address=(self.address, 0)) as remote:
                        remote.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        channel = Channel(context, remote, False, self.cancelled)
                        deadline = time.monotonic() + 8
                        channel.call(channel.tls.do_handshake, deadline)
                        cert = channel.tls.get_peer_certificate(as_cryptography=True)
                        if cert is None or not hmac.compare_digest(cert.fingerprint(hashes.SHA256()), fingerprint):
                            raise ValueError('Certificate mismatch')
                        channel.send(secret.hex(), deadline)
                        if channel.receive(deadline) != 'accepted':
                            raise ValueError('Tunnel rejected')
                        self.bridge(channel, raw, serving, epoch)
        except PEER_ERRORS:
            pass  # Consumer receives EOF; never log endpoints, credentials or payloads.
        finally:
            self.slots.release()

    def bridge(self, channel, plain, serving, epoch):
        plain.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        plain.setblocking(False)
        tls = channel.tls
        to_plain = bytes(channel.buffer)
        channel.buffer.clear()
        to_tls = b''
        sending = b''
        activity = time.monotonic()
        while not self.cancelled.is_set() and (not serving or (self.allowed.is_set() and epoch == self.epoch)):
            if time.monotonic() - activity > 600:
                raise TimeoutError
            reads = ([plain] if len(to_tls) < 262144 else []) + ([channel.raw] if len(to_plain) < 262144 else [])
            writes = ([plain] if to_plain else []) + ([channel.raw] if to_tls or sending else [])
            readable, writable, _ = select.select(reads, writes, [], 0 if tls.pending() and len(to_plain) < 262144 else .1)
            if plain in readable:
                data = plain.recv(65536)
                if not data:
                    return
                to_tls += data
                activity = time.monotonic()
            if channel.raw in readable or (tls.pending() and len(to_plain) < 262144):
                try:
                    data = tls.recv(65536)
                    if not data:
                        return
                    to_plain += data
                    self.transferred[0] += len(data)
                    activity = time.monotonic()
                except (SSL.WantReadError, SSL.WantWriteError):
                    pass
            if plain in writable:
                try:
                    to_plain = to_plain[plain.send(to_plain):]
                    activity = time.monotonic()
                except BlockingIOError:
                    pass
            if channel.raw in writable:
                if not sending:
                    sending, to_tls = to_tls[:65536], to_tls[65536:]
                try:
                    sent = tls.send(sending)
                    self.transferred[1] += sent
                    sending = sending[sent:]
                    activity = time.monotonic()
                except (SSL.WantReadError, SSL.WantWriteError):
                    pass
