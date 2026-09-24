"""Conservative receive-side evidence for the YouTube failover hold.

Conntrack counters are not proof of playback or application delivery. They
only show enough incoming traffic to justify a short, reversible deferral.
Outgoing retries, TCP acknowledgements and old cumulative totals do not.
"""
import re


def reply_counters(line):
    if re.search(r'\btcp\b', line) and ' ESTABLISHED ' not in line:
        return None
    if not re.search(r'\b(?:tcp|udp)\b', line):
        return None
    packets = re.findall(r'\bpackets=(\d+)', line)
    counts = re.findall(r'\bbytes=(\d+)', line)
    if len(packets) != 2 or len(counts) != 2:
        return None
    return {'reply_packets': int(packets[1]), 'reply_bytes': int(counts[1])}


def incoming_progress(current, previous, *, minimum_bytes):
    if not current or not previous or not all(field in previous for field in ('reply_packets', 'reply_bytes')):
        return False
    packets = current['reply_packets'] - previous['reply_packets']
    byte_count = current['reply_bytes'] - previous['reply_bytes']
    if packets <= 0 or byte_count <= 0:
        return False
    # A conservative allowance for IP/TCP headers, options and pure ACKs.
    # This is deliberately a lower estimate of incoming payload, not bitrate.
    return byte_count - 128 * packets >= max(8192, int(minimum_bytes))


def defer_control_failure(state, *, now, maximum_seconds=45, maximum_failures=3):
    """Repeated failed control checks must reach a multi-endpoint confirmation."""
    count = int(state.get('transient_control_failures') or 0) + 1
    since = float(state.get('transient_control_since') or now)
    if now < since:
        since = now
    state['transient_control_failures'] = count
    state['transient_control_since'] = since
    return count < maximum_failures and now - since < maximum_seconds


def reset_control_failures(state):
    state['transient_control_failures'] = 0
    state['transient_control_since'] = 0.0
