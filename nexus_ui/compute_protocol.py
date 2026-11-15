"""Closed schema for compute control over the already authenticated pairing channel."""
import re
from .compute_plan import validate_profile, REVISION


def validate_compute(message):
    action = message.get('action')
    base = {'type', 'action'}
    if action == 'off' and message.keys() == base:
        return
    if action == 'ready' and message.keys() == base | {'profile', 'code', 'sha256', 'revision'}:
        from .pairing_transport import read_invitation, valid_digest
        validate_profile(message['profile'])
        if not isinstance(message['code'], str):
            raise ValueError('Invalid compute invitation')
        read_invitation(message['code'])
        if valid_digest(message['sha256']) and message['revision'] == REVISION:
            return
    if action in ('request', 'accepted', 'rejected', 'end') and message.keys() == base | {'id'}:
        if isinstance(message['id'], str) and re.fullmatch('[0-9a-f]{32}', message['id']):
            return
    if action == 'activity' and message.keys() == base | {'id', 'graphs'}:
        if (isinstance(message['id'], str) and re.fullmatch('[0-9a-f]{32}', message['id'])
                and type(message['graphs']) is int and 0 <= message['graphs'] <= 10**9):
            return
    raise ValueError('Unsupported compute message; update both applications')
