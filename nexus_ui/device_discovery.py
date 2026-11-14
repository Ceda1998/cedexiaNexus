"""Opt-in IPv4 link-local announcements on the selected network interface."""
from dataclasses import dataclass
from ipaddress import IPv4Network
import struct
import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QAbstractSocket, QHostAddress, QNetworkInterface, QUdpSocket

from .pairing_transport import lan_address


GROUP = QHostAddress("239.255.73.65")
PORT = 49765
ANNOUNCEMENT = struct.Struct("!4sBH32s")
PLATFORMS = ("Gerät", "macOS", "Windows")
PEER_TTL = 5
MAX_PEERS = 32


@dataclass(frozen=True)
class DiscoveredPeer:
    address: str
    port: int
    fingerprint: bytes
    platform: int

    @property
    def label(self):
        return f"{PLATFORMS[self.platform]} · {self.fingerprint.hex()[:8].upper()}"

    @property
    def target(self):
        return self.address, self.port, self.fingerprint, None


def network_interface(address):
    for interface in QNetworkInterface.allInterfaces():
        for entry in interface.addressEntries():
            if entry.ip().toString() == address and 0 < entry.prefixLength() < 32:
                return interface, IPv4Network((address, entry.prefixLength()), strict=False)
    raise ValueError("Local interface or IPv4 subnet unavailable.")


def parse_announcement(data, sender, network, own_fingerprint):
    if len(data) != ANNOUNCEMENT.size or lan_address(sender) not in network:
        raise ValueError("Invalid local announcement.")
    signature, system, port, fingerprint = ANNOUNCEMENT.unpack(data)
    if signature != b"CN01" or system >= len(PLATFORMS) or not port or fingerprint == own_fingerprint:
        raise ValueError("Invalid local announcement.")
    return DiscoveredPeer(sender, port, fingerprint, system)


class DeviceDiscovery(QObject):
    changed = Signal()
    interrupted = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.listener = QUdpSocket(self)
        self.sender = QUdpSocket(self)
        self.listener.readyRead.connect(self.read)
        self.timer = QTimer(self, interval=1500)
        self.timer.timeout.connect(self.tick)
        self.peers = {}
        self.network = None
        self.payload = b""
        self.fingerprint = b""
        self.interface_index = 0

    def start(self, address, interface, network, system, port, fingerprint):
        self.close()
        flags = (QAbstractSocket.BindFlag.ShareAddress | QAbstractSocket.BindFlag.ReuseAddressHint)
        if (not self.listener.bind(QHostAddress(QHostAddress.SpecialAddress.AnyIPv4), PORT, flags)
                or not self.listener.joinMulticastGroup(GROUP, interface)
                or not self.sender.bind(QHostAddress(address), 0)):
            self.close()
            return False
        self.sender.setMulticastInterface(interface)
        self.sender.setSocketOption(QAbstractSocket.SocketOption.MulticastTtlOption, 1)
        self.network = network
        self.interface_index = interface.index()
        self.fingerprint = fingerprint
        self.payload = ANNOUNCEMENT.pack(b"CN01", system, port, fingerprint)
        self.timer.start()
        self.tick()
        return self.timer.isActive()

    def tick(self):
        if self.sender.writeDatagram(self.payload, GROUP, PORT) != len(self.payload):
            self.close()
            self.interrupted.emit()
            return
        now = time.monotonic()
        old_count = len(self.peers)
        self.peers = {key: value for key, value in self.peers.items() if value[1] > now}
        if old_count != len(self.peers):
            self.changed.emit()

    def read(self):
        changed = False
        for _ in range(64):
            if not self.listener.hasPendingDatagrams() or self.network is None:
                break
            datagram = self.listener.receiveDatagram(ANNOUNCEMENT.size + 1)
            if datagram.interfaceIndex() not in (0, self.interface_index):
                continue
            try:
                peer = parse_announcement(bytes(datagram.data()), datagram.senderAddress().toString(),
                                          self.network, self.fingerprint)
            except ValueError:
                continue
            previous = self.peers.get(peer.fingerprint)
            if previous is None and len(self.peers) >= MAX_PEERS:
                continue
            changed |= previous is None or previous[0] != peer
            self.peers[peer.fingerprint] = (peer, time.monotonic() + PEER_TTL)
        if changed:
            self.changed.emit()
        if self.listener.hasPendingDatagrams() and self.network is not None:
            QTimer.singleShot(0, self.read)

    def close(self):
        self.timer.stop()
        self.listener.close()
        self.sender.close()
        self.network = None
        self.peers.clear()
        self.changed.emit()
