"""Bounded two-GPU planning; benchmark estimates never imply measured dual-host speed."""
from dataclasses import dataclass
import math
import re

REVISION = '8ca5a8008b57aa39f2601546c0d07912045080a5'
DEVICE = re.compile(r'^\s*(MTL\d+|CUDA\d+|RPC\d+): (.+) \((\d+) MiB, (\d+) MiB free\)', re.M)


def devices(text):
    return [dict(device=m[1], name=m[2][:120], total=int(m[3]), free=int(m[4]))
            for m in DEVICE.finditer(text)]


def validate_profile(value):
    if not isinstance(value, dict) or value.keys() != {'device', 'name', 'total', 'free', 'tps'}:
        raise ValueError('Invalid GPU profile')
    if (not isinstance(value['device'], str) or not re.fullmatch(r'(MTL|CUDA)\d+', value['device'])
            or not isinstance(value['name'], str) or not 0 < len(value['name']) <= 120
            or not value['name'].isprintable()
            or type(value['total']) is not int or not 0 < value['total'] <= 2**24
            or type(value['free']) is not int or not 0 < value['free'] <= value['total']
            or type(value['tps']) not in (int, float) or not math.isfinite(value['tps'])
            or not 0 <= value['tps'] < 1e7):
        raise ValueError('Invalid GPU profile')


@dataclass(frozen=True)
class Plan:
    local_layers: int
    remote_layers: int
    basis: str

    @property
    def split(self):
        return f'{self.local_layers},{self.remote_layers}'

    @property
    def description(self):
        return (f'Hier {self.local_layers} · Zweites Gerät {self.remote_layers} Schichten '
                f'· {self.basis}')


def plan_layers(local, remote, *, size, layers, embedding, context):
    for profile in (local, remote):
        validate_profile(profile)
    if not 2 <= layers <= 4096 or not 1 <= embedding <= 131072 or not 128 <= context <= 131072:
        raise ValueError('Modellmetadaten oder Kontext für die automatische Verteilung nicht unterstützt.')
    # Conservative KV estimate (full K/V width; overestimates GQA), 15% headroom,
    # plus 1 GiB scratch and 10% model overhead on EACH device.
    weight = size / 1024**2
    cost = weight / layers + 4 * context * embedding / 1024**2
    capacity = [max(0, int((p['free'] * .85 - 1024 - weight * .1) / cost)) for p in (local, remote)]
    # The final layer is the output head: remote must also own a repeating layer.
    lower, upper = max(1, layers - capacity[1]), min(layers - 2, capacity[0])
    if lower > upper:
        raise ValueError('Zu wenig freier GPU-Speicher für beide Anteile. Kontext verkleinern oder kleineres GGUF wählen.')
    measured = local['tps'] > 0 and remote['tps'] > 0
    scores = [p['tps'] if measured else p['free'] for p in (local, remote)]
    count = max(lower, min(upper, round(layers * scores[0] / sum(scores))))
    return Plan(count, layers - count, 'Kurzbenchmark, Schätzung' if measured else 'Speicherschätzung, Leistung ungemessen')
