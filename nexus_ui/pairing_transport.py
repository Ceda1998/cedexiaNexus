"""Single-use, certificate-pinned TLS sessions on an explicitly selected LAN interface."""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import ipaddress
import json
from queue import Empty, Queue
import re
import secrets
import select
import socket
import struct
from threading import Event
import time
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from OpenSSL import SSL
from PySide6.QtCore import QThread, Signal


LAN_NETWORKS = tuple(ipaddress.ip_network(net) for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
INVITE = struct.Struct("!4sH32s32s")
MAX_MESSAGE = 4096
HANDSHAKE_SECONDS = 8
INVITE_SECONDS = 300
SESSION_SECONDS = 7200
PEER_ERRORS = (OSError, SSL.Error, ValueError, RecursionError)


def lan_address(value):
    address = ipaddress.IPv4Address(value)
    if not any(address in network for network in LAN_NETWORKS):
        raise ValueError("A private LAN IPv4 address is required.")
    return address


def make_invitation(address, port, fingerprint, secret):
    payload = INVITE.pack(lan_address(address).packed, port, fingerprint, secret)
    return "nexus1." + base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def read_invitation(code):
    if not re.fullmatch(r"nexus1\.[A-Za-z0-9_-]{94}", code):
        raise ValueError("Invalid invitation.")
    payload = base64.b64decode(code[7:] + "==", altchars=b"-_", validate=True)
    address, port, fingerprint, secret = INVITE.unpack(payload)
    if port == 0:
        raise ValueError("Invalid port.")
    return str(lan_address(address)), port, fingerprint, secret


def tls_context(server):
    context = SSL.Context(SSL.TLS_SERVER_METHOD if server else SSL.TLS_CLIENT_METHOD)
    context.set_min_proto_version(SSL.TLS1_3_VERSION)
    context.set_options(SSL.OP_NO_TICKET)
    return context


def host_context():
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "Cedexia Nexus LAN")])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(hours=3))
                   .sign(key, hashes.SHA256()))
    context = tls_context(server=True)
    context.use_certificate(certificate)
    context.use_privatekey(key)
    return context, certificate.fingerprint(hashes.SHA256())


def valid_source(value):
    if (not isinstance(value, str) or len(value) > 1600 or
            any(ord(char) < 33 or ord(char) > 126 for char in value) or "\\" in value):
        return False
    try:
        url = urlsplit(value)
        host = url.hostname or ""
        return (url.scheme == "https" and url.username is None and url.password is None
                and url.port in (None, 443) and url.query in ("", "download=true")
                and bool(re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z][a-z0-9-]*", host)))
    except ValueError:
        return False


def validate_message(message):
    if not isinstance(message, dict):
        raise ValueError("Invalid message.")
    kind = message.get("type")
    if kind == "model":
        state = message.get("state")
        if state in ("missing", "checking", "error") and message.keys() == {"type", "state"}:
            return
        name = message.get("name")
        if (state == "ready" and message.keys() == {"type", "state", "name", "size", "parts", "sha256"}
                and isinstance(name, str) and 0 < len(name) <= 255
                and name.isprintable() and "/" not in name and "\\" not in name
                and type(message.get("size")) is int and 0 < message["size"] < 2**63
                and type(message.get("parts")) is int and 1 <= message["parts"] <= 999
                and valid_digest(message.get("sha256"))):
            return
    if (kind == "source" and message.keys() == {"type", "sha256", "url"}
            and valid_digest(message.get("sha256")) and valid_source(message.get("url"))):
        return
    raise ValueError("Invalid message.")


def valid_digest(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


class Channel:
    def __init__(self, context, raw, server, stop):
        self.raw = raw
        self.raw.setblocking(False)
        self.tls = SSL.Connection(context, raw)
        if server:
            self.tls.set_accept_state()
        else:
            self.tls.set_connect_state()
        self.stop = stop
        self.buffer = bytearray()

    def call(self, function, deadline, *args):
        while not self.stop.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            try:
                return function(*args)
            except SSL.WantReadError:
                select.select([self.raw], [], [], min(remaining, 0.2))
            except SSL.WantWriteError:
                select.select([], [self.raw], [], min(remaining, 0.2))
        raise ConnectionAbortedError

    def send(self, message, deadline):
        data = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(data) > MAX_MESSAGE:
            raise ValueError("Message too large.")
        while data:
            sent = self.call(self.tls.send, deadline, data)
            data = data[sent:]

    def receive(self, deadline):
        while (index := self.buffer.find(b"\n")) < 0:
            if len(self.buffer) >= MAX_MESSAGE:
                raise ValueError("Message too large.")
            chunk = self.call(self.tls.recv, deadline, MAX_MESSAGE - len(self.buffer))
            if not chunk:
                raise ConnectionError
            self.buffer.extend(chunk)
        message = json.loads(bytes(self.buffer[:index]).decode("utf-8"))
        del self.buffer[:index + 1]
        return message


class PairingThread(QThread):
    invitation = Signal(str)
    connected = Signal()
    message = Signal(dict)
    ended = Signal(str)

    def __init__(self, *, address=None, code=None, parent=None):
        super().__init__(parent)
        if (address is None) == (code is None):
            raise ValueError("Select a local address or provide an invitation.")
        self.address = address
        self.target = read_invitation(code) if code is not None else None
        self.cancelled = Event()
        self.outgoing = Queue()
        self.joined = False

    def stop(self):
        self.cancelled.set()

    def send(self, message):
        validate_message(message)
        self.outgoing.put(message)

    def run(self):
        try:
            if self.target is None:
                self.host()
            else:
                self.join()
        except PEER_ERRORS:
            if self.joined:
                status = "Verbindung zum anderen Gerät beendet."
            elif self.target is None:
                status = "Einladung beendet. Prüfe bei Bedarf die LAN-Adresse und die Firewall."
            else:
                status = "Beitritt fehlgeschlagen. Prüfe Einladung, gemeinsames LAN und Firewall."
        else:
            status = "Einladung oder Sitzung abgelaufen."
        if self.cancelled.is_set():
            status = "Verbindung getrennt."
        self.ended.emit(status)

    def host(self):
        address = str(lan_address(self.address))
        context, fingerprint = host_context()
        secret = secrets.token_bytes(32)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            listener.bind((address, 0))
            listener.listen(1)
            listener.settimeout(0.2)
            self.invitation.emit(make_invitation(address, listener.getsockname()[1], fingerprint, secret))
            deadline = time.monotonic() + INVITE_SECONDS
            while not self.cancelled.is_set() and time.monotonic() < deadline:
                try:
                    raw, peer = listener.accept()
                except TimeoutError:
                    continue
                with raw:
                    try:
                        lan_address(peer[0])
                        channel = Channel(context, raw, True, self.cancelled)
                        handshake = min(deadline, time.monotonic() + HANDSHAKE_SECONDS)
                        channel.call(channel.tls.do_handshake, handshake)
                        proof = channel.receive(handshake)
                        if not isinstance(proof, str) or not re.fullmatch(r"[0-9a-f]{64}", proof):
                            continue
                        if not hmac.compare_digest(secret, bytes.fromhex(proof)):
                            continue
                        channel.send("accepted", handshake)
                    except PEER_ERRORS:
                        continue
                    listener.close()
                    self.exchange(channel)
                    return

    def join(self):
        address, port, fingerprint, secret = self.target
        with socket.create_connection((address, port), timeout=3) as raw:
            channel = Channel(tls_context(server=False), raw, False, self.cancelled)
            deadline = time.monotonic() + HANDSHAKE_SECONDS
            channel.call(channel.tls.do_handshake, deadline)
            certificate = channel.tls.get_peer_certificate(as_cryptography=True)
            if certificate is None or not hmac.compare_digest(certificate.fingerprint(hashes.SHA256()), fingerprint):
                raise ValueError("Certificate does not match the invitation.")
            channel.send(secret.hex(), deadline)
            if channel.receive(deadline) != "accepted":
                raise ValueError("Invitation was rejected.")
            self.exchange(channel)

    def exchange(self, channel):
        self.joined = True
        self.connected.emit()
        expires = time.monotonic() + SESSION_SECONDS
        while not self.cancelled.is_set() and time.monotonic() < expires:
            try:
                outgoing = self.outgoing.get_nowait()
            except Empty:
                pass
            else:
                channel.send(outgoing, time.monotonic() + HANDSHAKE_SECONDS)
            try:
                incoming = channel.receive(time.monotonic() + 0.2)
            except TimeoutError:
                continue
            validate_message(incoming)
            if incoming["type"] == "source" and self.target is None:
                raise ValueError("Only the inviting device can share a source.")
            self.message.emit(incoming)
