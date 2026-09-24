"""Bounded route measurements; HTTP timing is never labelled UDP/game latency.

No network, persistence, routing or process mutations happen in this module.
Evidence is scoped to one device/destination/WAN/candidate/endpoint/generation.
"""
from dataclasses import dataclass
import math
import statistics


TEST_KINDS = frozenset(('https', 'udp_echo'))
MAX_SAMPLES = 64


def _finite(value, low=0.0, high=86400.0):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('Invalid measurement number')
    return float(value)


def _identifier(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 128 or
            any(not (c.isascii() and (c.isalnum() or c in '._:-')) for c in value)):
        raise ValueError('Invalid measurement identity')
    return value


@dataclass(frozen=True)
class RouteIdentity:
    device: str
    destination: str
    wan: str
    protocol: str
    key_id: str
    transport: str
    endpoint_id: str
    test_kind: str
    generation: int

    def __post_init__(self):
        for name in ('device', 'destination', 'wan', 'protocol', 'key_id', 'transport', 'endpoint_id'):
            _identifier(getattr(self, name))
        if self.protocol not in ('direct', 'vless', 'vless2', 'vmess', 'trojan', 'shadowsocks', 'hysteria2'):
            raise ValueError('Unknown candidate protocol')
        if self.test_kind not in TEST_KINDS or type(self.generation) is not int or self.generation < 0:
            raise ValueError('Invalid measurement scope')

    @property
    def comparison_scope(self):
        # WAN and key identify competing paths, not different destinations.
        return (self.device, self.destination, self.endpoint_id, self.test_kind)


@dataclass(frozen=True)
class ProbeReply:
    sequence: int
    elapsed_ms: float

    def __post_init__(self):
        if type(self.sequence) is not int or not 0 <= self.sequence < MAX_SAMPLES:
            raise ValueError('Invalid probe sequence')
        _finite(self.elapsed_ms, high=120000)


@dataclass(frozen=True)
class MeasurementWindow:
    identity: RouteIdentity
    started_at: float
    finished_at: float
    sent: int
    deadline_ms: float
    replies: tuple
    wan_verified: bool
    udp_associate_verified: bool = False
    source_verified: bool = False

    def __post_init__(self):
        if not isinstance(self.identity, RouteIdentity):
            raise ValueError('Invalid route identity')
        start = _finite(self.started_at, high=1e12)
        end = _finite(self.finished_at, high=1e12)
        if not 0 <= end - start <= 180 or type(self.sent) is not int or not 1 <= self.sent <= MAX_SAMPLES:
            raise ValueError('Invalid measurement window')
        _finite(self.deadline_ms, low=1, high=30000)
        if not isinstance(self.replies, tuple) or len(self.replies) > self.sent * 2:
            raise ValueError('Unbounded measurement replies')
        for reply in self.replies:
            if not isinstance(reply, ProbeReply) or reply.sequence >= self.sent:
                raise ValueError('Reply does not belong to this window')
        if any(type(value) is not bool for value in
               (self.wan_verified, self.udp_associate_verified, self.source_verified)):
            raise ValueError('Invalid measurement evidence')


def window_metrics(window, *, now, ttl_seconds=900, minimum_samples=20):
    """Loss is deadline misses; late unique replies are reported separately.

    Jitter is mean absolute difference of adjacent successful request RTTs,
    ordered by sequence (not arrival order). p95 uses nearest rank. HTTP
    failures are availability failures, never packet loss or UDP capability.
    """
    if not isinstance(window, MeasurementWindow):
        raise ValueError('Invalid measurement window')
    now = _finite(now, high=1e12)
    ttl_seconds = _finite(ttl_seconds, low=1, high=86400)
    if type(minimum_samples) is not int or not 2 <= minimum_samples <= MAX_SAMPLES:
        raise ValueError('Invalid sample threshold')
    unique = {}
    for reply in window.replies:
        unique[reply.sequence] = min(reply.elapsed_ms, unique.get(reply.sequence, math.inf))
    timely = [(seq, rtt) for seq, rtt in sorted(unique.items()) if rtt <= window.deadline_ms]
    latencies = [rtt for _, rtt in timely]
    late = sum(rtt > window.deadline_ms for rtt in unique.values())
    failures = window.sent - len(timely)
    reason = ''
    if now < window.finished_at or window.finished_at - window.started_at < 0:
        reason = 'clock_changed'
    elif now - window.finished_at > ttl_seconds:
        reason = 'stale'
    elif not window.source_verified:
        reason = 'source_unverified'
    elif not window.wan_verified:
        reason = 'wan_unverified'
    elif window.identity.test_kind == 'udp_echo' and not window.udp_associate_verified and window.identity.protocol != 'direct':
        reason = 'udp_unverified'
    elif window.sent < minimum_samples:
        reason = 'insufficient_samples'
    elif len(timely) < 2:
        reason = 'unavailable'
    ordered = sorted(latencies)
    udp = window.identity.test_kind == 'udp_echo'
    return {
        'eligible': not reason, 'reason': reason, 'sent': window.sent,
        'received_on_time': len(timely), 'late_replies': late,
        'duplicates': len(window.replies) - len(unique),
        'success_rate': len(timely) / window.sent,
        'loss_rate': failures / window.sent if udp else None,
        'http_failure_rate': failures / window.sent if not udp else None,
        'median_ms': statistics.median(latencies) if latencies else None,
        'p95_ms': ordered[math.ceil(.95 * len(ordered)) - 1] if ordered else None,
        'jitter_ms': statistics.mean(abs(b-a) for a,b in zip(latencies,latencies[1:])) if udp and len(latencies)>1 else None,
        'age_seconds': max(0, now-window.finished_at),
        'metric_kind': 'udp_echo_rtt' if udp else 'https_response_time',
    }


def recommend(windows, *, now, direct_allowed, required_kind, expected_generations,
              ttl_seconds=900, minimum_samples=20):
    """Compare only matching observations; return a recommendation, no apply."""
    if type(direct_allowed) is not bool or required_kind not in TEST_KINDS:
        raise ValueError('Invalid route policy')
    if not isinstance(windows, (tuple, list)) or len(windows) > 16:
        raise ValueError('Unbounded candidate list')
    scoped = None
    candidates = []
    excluded = []
    identities = set()
    for window in windows:
        if not isinstance(window, MeasurementWindow):
            raise ValueError('Invalid measurement window')
        identity = window.identity
        if identity in identities:
            raise ValueError('Duplicate candidate window')
        identities.add(identity)
        if scoped is None:
            scoped = identity.comparison_scope
        if identity.comparison_scope != scoped:
            raise ValueError('Measurements have different scopes')
        metrics = window_metrics(window, now=now, ttl_seconds=ttl_seconds, minimum_samples=minimum_samples)
        reason = metrics['reason']
        if identity.protocol == 'direct' and not direct_allowed:
            reason = 'direct_forbidden'
        elif identity.test_kind != required_kind:
            reason = 'wrong_measurement_kind'
        elif expected_generations.get((identity.protocol,identity.key_id,identity.wan)) != identity.generation:
            reason = 'generation_changed'
        if reason:
            excluded.append({'identity': identity, 'reason': reason})
            continue
        # Availability and tail latency precede the median. A fast route with
        # deadline misses must not outrank a stable fully available route.
        rank = (-metrics['success_rate'], metrics['late_replies']/metrics['sent'],
                metrics['p95_ms'], metrics['jitter_ms'] or 0, metrics['median_ms'])
        candidates.append((rank, identity, metrics))
    candidates.sort(key=lambda item: (item[0], repr(item[1])))
    return {'recommended': candidates[0][1] if candidates else None,
            'metrics': candidates[0][2] if candidates else None,
            'reason': 'measured_quality' if candidates else 'no_valid_measurements',
            'eligible_count': len(candidates), 'excluded': excluded}
