"""Applied-state receipts for a controlled executor, never inferred from disk.

This store contains only private digests and process identity, not key material.
The caller holds the coordinator during load/verify and rechecks its ticket.
record_loaded may ONLY follow a controlled, confirmed load by the executor.
"""
import math
from pathlib import Path

from proxy_apply_coordinator import _atomic_json, _read_json
from proxy_apply_plan import RuntimeEvidence, config_fingerprint


class AttestationStore:
    def __init__(self, path):
        self.path = Path(path)

    def _read(self):
        try:
            value = _read_json(self.path)
            if (not isinstance(value, dict) or value.get('schema') != 1 or
                    not isinstance(value.get('process_identity'), str) or not value['process_identity'] or
                    type(value.get('generation')) is not int or value['generation'] < 0 or
                    not isinstance(value.get('applied_fingerprint'), str) or
                    not isinstance(value.get('observed_fingerprint'), str) or
                    not isinstance(value.get('health'), dict)):
                return None
            for health in value['health'].values():
                if (not isinstance(health, dict) or type(health.get('healthy')) is not bool or
                        type(health.get('checked_at')) not in (int, float) or
                        not math.isfinite(health['checked_at'])):
                    return None
            return value
        except (OSError, ValueError, TypeError):
            return None

    def record_loaded(self, config, *, process_identity, generation, observed_fingerprint):
        if (not isinstance(process_identity, str) or not process_identity or
                type(generation) is not int or generation < 0 or
                not isinstance(observed_fingerprint, str) or not observed_fingerprint):
            raise ValueError('Invalid controlled-load attestation')
        _atomic_json(self.path, {
            'schema': 1, 'process_identity': process_identity, 'generation': generation,
            'applied_fingerprint': config_fingerprint(config),
            'observed_fingerprint': observed_fingerprint, 'health': {},
        })

    def record_health(self, protocol, *, config, process_identity, generation,
                      observed_fingerprint, checked_at, healthy):
        if (type(healthy) is not bool or type(checked_at) not in (int, float) or
                not math.isfinite(checked_at) or not isinstance(protocol, str) or
                protocol not in ('vless', 'vless2', 'vmess', 'trojan', 'shadowsocks', 'hysteria2')):
            raise ValueError('Invalid data-plane evidence')
        state = self._read()
        if (state is None or state['process_identity'] != process_identity or
                state['generation'] != generation or
                state['observed_fingerprint'] != observed_fingerprint or
                state['applied_fingerprint'] != config_fingerprint(config)):
            return False
        state['health'][protocol] = {'checked_at': checked_at, 'healthy': healthy}
        _atomic_json(self.path, state)
        return True

    def evidence(self, protocol, *, observed_fingerprint):
        state = self._read()
        if state is None or state['observed_fingerprint'] != observed_fingerprint:
            return None
        health = state['health'].get(protocol, {})
        return RuntimeEvidence(
            applied_fingerprint=state['applied_fingerprint'],
            verified_fingerprint=state['applied_fingerprint'] if health else '',
            process_identity=state['process_identity'], generation=state['generation'],
            checked_at=health.get('checked_at', 0), healthy=health.get('healthy'),
        )
