"""Opt-in desktop lifecycle for two-device inference (NX-011)."""
import json
import re
import secrets
import socket

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal
from .compute_plan import devices, REVISION
from .compute_tunnel import Tunnel
from .device_pairing import same_weights


class DistributedSession(QObject):
    changed = Signal()

    def __init__(self, runner, pairing):
        super().__init__(pairing)
        self.runner, self.pairing = runner, pairing
        self.profile = self.peer = self.server = self.proxy = None
        self.probe = self.worker = None
        self.processes = set()
        self.threads = set()
        self.enabled = False
        self.prepared = False
        self.pending = self.reservation = None
        self.launched = False
        self.graphs = self.peer_graphs = 0
        self.last_run = None
        self.worker_tail = ''
        self.prompt = ''
        self.digest = None
        self.message = 'Auf beiden Geräten im Gerätefenster gemeinsames Rechnen aktivieren.'
        self.timer = QTimer(self, singleShot=True, interval=30000)
        self.timer.timeout.connect(lambda: self.cancel('Das zweite Gerät hat nicht rechtzeitig geantwortet.'))
        self.lease = QTimer(self, singleShot=True, interval=1800000)
        self.lease.timeout.connect(lambda: self.disable('Zeitlimit für den gemeinsamen Lauf erreicht.'))
        self.activity_timer = QTimer(self, interval=1000)
        self.activity_timer.timeout.connect(self.publish_activity)
        self.activity_timer.start()
        pairing.compute_message.connect(self.receive)
        pairing.compute_rejected.connect(self.disable)
        pairing.state_changed.connect(self.check_state)
        runner.finished.connect(self.run_finished)
        runner.model_changed.connect(lambda: self.disable('Modell geändert; gemeinsam neu vorbereiten.'))

    @property
    def busy(self):
        return bool(self.pending or self.reservation or self.probe or self.processes or self.threads)

    @property
    def ready(self):
        return bool(self.compatible and self.prepared and self.enabled and self.server and self.peer and self.profile and self.matches()
                    and not self.pending and not self.reservation and not self.runner.busy)

    @property
    def compatible(self):
        return bool(self.pairing.connected and self.pairing.thread
                    and self.pairing.thread.compute_compatible)

    def blocked_reason(self):
        if not self.pairing.connected:
            return (getattr(self.pairing, 'connection_failure', '') or
                    'Kein Gerät verbunden. Geräte verbinden und Gewichte abgleichen.')
        if not self.compatible:
            return ('CN-VERSION: Die Gegenstelle bestätigt das Rechenprotokoll nicht. '
                    'Beide Apps auf mindestens 0.1.72 aktualisieren und neu koppeln. '
                    'Der Gewichte-Abgleich bleibt verfügbar.')
        if not self.matches():
            return 'Die GGUF-Gewichte müssen auf beiden Geräten fertig geprüft und identisch sein.'
        if not self.enabled:
            return self.message + ' Hier im Gerätefenster gemeinsames Rechnen aktivieren.'
        if not self.prepared:
            return 'Dieses Gerät wird vorbereitet. ' + self.message
        if self.pending or self.reservation:
            return self.message
        if not self.peer:
            return 'Dieses Gerät ist bereit. Auf dem zweiten Gerät gemeinsames Rechnen aktivieren und den GPU-Test abwarten.'
        return ''

    def matches(self):
        return self.pairing.connected and self.pairing.peer_model and same_weights(self.pairing.local_model, self.pairing.peer_model)

    def tell(self, action, **fields):
        if self.compatible:
            self.pairing.thread.send({'type': 'compute', 'action': action, **fields})

    def status(self, text):
        self.message = text
        self.changed.emit()

    def check_state(self):
        if not self.pairing.connected:
            self.peer = None
        if self.enabled and (not self.matches() or self.pairing.local_model.get('sha256') != self.digest):
            self.disable('Gewichte oder Verbindung geändert; gemeinsames Rechnen erneut aktivieren.')
        self.changed.emit()

    def runtime_file(self, name):
        return self.runner.runtime.with_name(name + ('.exe' if self.runner.windows else ''))

    def process(self, program, args, done, timeout=30000, on_chunk=None):
        proc = QProcess(self)
        self.processes.add(proc)
        proc.setWorkingDirectory(str(self.runner.runtime.parent))
        env = QProcessEnvironment.systemEnvironment()
        for key in env.keys():
            if key.startswith(('LLAMA_', 'GGML_')):
                env.remove(key)
        env.insert('GGML_RPC_NO_RDMA', '1')
        if on_chunk:
            env.insert('GGML_RPC_DEBUG', '1')
        proc.setProcessEnvironment(env)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        buffer = bytearray()
        clock = QTimer(proc, singleShot=True, interval=timeout)
        clock.timeout.connect(proc.kill)
        def drain():
            chunk = bytes(proc.readAllStandardOutput())
            if on_chunk:
                on_chunk(chunk)
            buffer.extend(chunk)
            if len(buffer) > 131072:
                del buffer[:-131072]
        proc.readyReadStandardOutput.connect(drain)
        def finish(code):
            if proc not in self.processes:
                return
            drain()
            self.processes.remove(proc)
            clock.stop()
            if self.probe is proc:
                self.probe = None
            done(code, buffer.decode('utf-8', errors='replace'))
            proc.deleteLater()
            self.changed.emit()
        proc.finished.connect(lambda code, _: finish(code))
        proc.errorOccurred.connect(lambda error: finish(-1) if error == QProcess.ProcessError.FailedToStart else None)
        proc.start(str(program), args)
        clock.start()
        return proc

    def enable(self):
        if self.enabled or self.runner.busy or self.busy:
            return
        if not self.matches():
            self.status('Zuerst beide Geräte verbinden und identische GGUF-Gewichte prüfen.')
            return
        if not self.compatible:
            self.status(self.blocked_reason())
            return
        if not all(self.runtime_file(name).is_file() for name in ('llama-completion', 'llama-bench', 'ggml-rpc-server')):
            self.status('RPC-Runtime fehlt. Auf beiden Geräten den aktuellen Installer installieren.')
            return
        self.enabled = True
        self.prepared = False
        self.digest = self.pairing.local_model['sha256']
        self.runner.external_busy = True
        self.status('GPU und Runtime werden geprüft …')
        self.probe = self.process(self.runner.runtime, ['--version'], self.version_checked)

    def version_checked(self, code, text):
        if not self.enabled:
            return
        match = re.search(r'\bcommit ([0-9a-f]{8,40})\)', text)
        if code or not match or not REVISION.startswith(match[1]):
            self.disable('Runtime-Revision stimmt nicht überein. Aktuellen Installer verwenden.')
            return
        self.probe = self.process(self.runner.runtime, ['--offline', '--list-devices'], self.gpu_checked)

    def gpu_checked(self, code, text):
        if not self.enabled:
            return
        candidates = [d for d in devices(text) if d['device'].startswith(('CUDA', 'MTL'))]
        if code or not candidates:
            self.disable('Keine verwendbare CUDA-/Metal-GPU gefunden. Treiber und Runtime prüfen.')
            return
        self.profile = max(candidates, key=lambda d: d['free'])
        self.profile['tps'] = 0.0
        size = self.pairing.local_model['size'] / 1024**2
        if size * 1.2 + 2048 > self.profile['free'] * .85:
            self.start_worker()  # Model does not fit solo: never benchmark through CPU spill.
            return
        self.status('Kurzer lokaler GPU-Test mit dem ausgewählten GGUF …')
        self.probe = self.process(self.runtime_file('llama-bench'), [
            '-m', str(self.runner.model), '-dev', self.profile['device'], '-ngl', '999',
            '-p', '0', '-n', '16', '-r', '1', '-o', 'json', '-t', '4'], self.bench_finished, 180000)

    def bench_finished(self, code, text):
        if not self.enabled:
            return
        if code == 0:
            try:
                text = text.replace('\r\n', '\n')
                begin = text.index('[\n')
                report, _ = json.JSONDecoder().raw_decode(text[begin:])
                speed = float(report[0]['avg_ts'])
                if 0 < speed < 1e7:
                    self.profile['tps'] = speed
            except (ValueError, KeyError, IndexError, TypeError):
                pass
        self.start_worker()

    def start_worker(self):
        if not self.enabled:
            return
        self.status('Geschützter Worker wird vorbereitet …')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        worker = self.process(self.runtime_file('ggml-rpc-server'), [
            '--host', '127.0.0.1', '--port', str(port), '--device', self.profile['device']],
            lambda code, text: self.worker_ended(worker), 7200000, on_chunk=self.worker_activity)
        self.worker = worker
        # Check loopback readiness rather than assume a fixed startup delay.
        poll = QTimer(worker, interval=100)
        attempts = [0]
        def check():
            attempts[0] += 1
            if not self.enabled or self.worker is not worker:
                poll.stop()
                return
            # Loopback readiness probe carries no RPC payload and closes immediately.
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.02):
                    pass
            except OSError:
                if attempts[0] >= 150:
                    poll.stop()
                    self.disable('Worker konnte nicht starten. Runtime und freien GPU-Speicher prüfen.')
                return
            poll.stop()
            thread = self.pairing.thread
            self.server = self.track(Tunnel(address=thread.local_address, peer=thread.peer_address,
                                            worker_port=port, parent=self))
            self.server.ready.connect(self.advertise)
            self.server.start()
        poll.timeout.connect(check)
        poll.start()

    def worker_ended(self, worker):
        if self.worker is worker:
            self.worker = None
            if self.enabled:
                self.disable('Rechen-Worker wurde beendet. Gemeinsam neu vorbereiten.')

    def worker_activity(self, chunk):
        lines = (self.worker_tail + chunk.decode('utf-8', errors='replace')).split('\n')
        self.worker_tail = lines.pop()[-2048:]
        if self.reservation:
            self.graphs += sum(bool(re.search(r'\[graph_(?:re)?compute\] device:', line)) for line in lines)

    def publish_activity(self):
        if self.reservation:
            self.tell('activity', id=self.reservation, graphs=min(self.graphs, 10**9))

    def track(self, thread):
        self.threads.add(thread)
        thread.failed.connect(lambda: self.disable('Geschützter Rechenkanal fehlgeschlagen. Verbindung erneut herstellen.'))
        def finished():
            self.threads.discard(thread)
            thread.deleteLater()
            self.changed.emit()
        thread.finished.connect(finished)
        return thread

    def advertise(self, code):
        if not self.enabled:
            return
        self.runner.external_busy = False
        self.prepared = True
        self.tell('ready', profile=self.profile, code=code, sha256=self.digest, revision=REVISION)
        self.status(self.profile_text())

    def profile_text(self):
        def describe(profile):
            if not profile:
                return 'noch nicht vorbereitet'
            speed = f"{profile['tps']:.1f} Token/s im Kurztest" if profile['tps'] else 'Leistung ungemessen'
            return f"{profile['name']} · {profile['free'] / 1024:.1f} GiB frei · {speed}"
        return f"Hier: {describe(self.profile)}\nZweites Gerät: {describe(self.peer['profile'] if self.peer else None)}"

    def receive(self, message):
        if not self.compatible:
            self.status(self.blocked_reason())
            return
        action = message['action']
        if action == 'ready':
            from .pairing_transport import read_invitation
            if (self.pairing.local_model.get('sha256') != message['sha256'] or
                    read_invitation(message['code'])[0] != self.pairing.thread.peer_address):
                return
            self.peer = message
            self.status(self.profile_text())
        elif action == 'off':
            self.peer = None
            if self.pending or self.reservation or self.runner.distributed:
                self.cancel('Das zweite Gerät hat gemeinsames Rechnen beendet.')
            self.changed.emit()
        elif action == 'request':
            if not self.ready or self.runner.external_busy:
                self.tell('rejected', id=message['id'])
                return
            self.reservation = message['id']
            self.graphs = 0
            self.runner.external_busy = True
            self.server.allow()
            self.lease.start()
            self.tell('accepted', id=self.reservation)
            self.status('Dieses Gerät rechnet für den gemeinsamen Chat. Stoppen beendet den Lauf auf beiden Geräten.')
        elif action == 'accepted' and message['id'] == self.pending and self.proxy is None:
            self.timer.stop()
            thread = self.pairing.thread
            self.proxy = self.track(Tunnel(address=thread.local_address, peer=thread.peer_address,
                                           invitation=self.peer['code'], parent=self))
            self.proxy.ready.connect(self.launch)
            self.proxy.start()
        elif action == 'rejected' and message['id'] == self.pending:
            self.cancel('Das zweite Gerät ist beschäftigt. Bitte erneut senden.')
        elif action == 'end' and message['id'] in (self.reservation, self.pending):
            self.publish_activity()
            self.cancel('Gemeinsamer Lauf vom anderen Gerät beendet.', notify=False)
        elif action == 'activity' and message['id'] in (self.pending, self.last_run):
            self.peer_graphs = max(self.peer_graphs, message['graphs'])
            if not self.pending:
                self.status(f'Letzter Lauf: {self.peer_graphs} Rechengraphen vom zweiten Gerät gemeldet. '
                            'Backend-Zuweisung steht an der Chat-Antwort.')

    def start(self, prompt):
        if not self.ready or self.runner.external_busy:
            self.runner.status.emit(self.message)
            return False
        self.pending = secrets.token_hex(16)
        self.last_run = self.pending
        self.peer_graphs = 0
        self.launched = False
        self.prompt = prompt
        self.runner.external_busy = True
        self.tell('request', id=self.pending)
        self.timer.start()
        self.status('Zweites Gerät wird für diesen Lauf reserviert …')
        self.runner.status.emit(self.message)
        return True

    def launch(self, port):
        if not self.pending or not self.ready_for_launch():
            return
        self.runner.external_busy = False
        self.runner.distributed = {'endpoint': f'127.0.0.1:{int(port)}', 'local': dict(self.profile),
                                   'remote': dict(self.peer['profile']), 'size': self.pairing.local_model['size']}
        prompt, self.prompt = self.prompt, ''
        self.launched = True
        if not self.runner.start(prompt):
            self.launched = False
            self.cancel('Gemeinsamer Lauf konnte nicht starten.')

    def ready_for_launch(self):
        return self.enabled and self.peer and self.matches()

    def cancel(self, reason='Gemeinsamer Lauf gestoppt.', notify=True):
        request = self.pending or self.reservation
        own_pending = self.pending is not None and not self.launched
        self.launched = False
        self.pending = self.reservation = None
        self.prompt = ''
        self.timer.stop()
        self.lease.stop()
        if notify and request:
            self.tell('end', id=request)
        if self.server:
            self.server.revoke()
        if self.proxy:
            self.proxy.stop()
            self.proxy = None
        self.runner.external_busy = False
        if self.runner.distributed and self.runner.busy:
            self.runner.stop(reason)
        else:
            self.runner.distributed = None
            if own_pending:
                self.runner.finished.emit(reason)
        self.status(reason)

    def run_finished(self, _):
        if self.pending:
            self.cancel('Gemeinsamer Lauf beendet. Beide Geräte sind wieder verfügbar.')

    def disable(self, reason='Gemeinsames Rechnen deaktiviert.'):
        was_enabled = self.enabled
        self.enabled = False
        self.prepared = False
        self.cancel(reason)
        if was_enabled:
            self.tell('off')
        self.profile = None
        self.server = None
        self.probe = self.worker = None
        for thread in tuple(self.threads):
            thread.stop()
        for proc in tuple(self.processes):
            proc.kill()
        self.runner.external_busy = False
        self.status(reason)
