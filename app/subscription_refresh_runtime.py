import time

import subscription_runtime


def refresh_subscription_once(
    proto,
    record,
    *,
    source='auto',
    auto_refresh_allowed,
    fetch_keys,
    add_keys_to_pool,
    update_record,
    write_log,
    time_provider=time.time,
):
    """Refresh one managed subscription without owning application state."""
    record = record if isinstance(record, dict) else {}
    url = str(record.get('url') or '').strip()
    if not url or not bool(record.get('hwid_enabled')):
        return False
    if source == 'auto' and not auto_refresh_allowed(proto):
        return False

    attempt_at = float(time_provider())
    try:
        fetched, error = fetch_keys(url, use_router_hwid=True)
        if error:
            raise ValueError(error)
        selected_keys = subscription_runtime.subscription_keys_for_protocol(proto, fetched)
        if not selected_keys:
            raise ValueError('subscription did not return keys for the selected protocol')
        previous_managed_keys = record.get('managed_keys', [])
        suspicious_shrink = subscription_runtime.subscription_sync_shrink_is_suspicious(
            previous_managed_keys,
            selected_keys,
        )
        if suspicious_shrink and source == 'auto':
            update_record(
                proto,
                url=url,
                hwid_enabled=True,
                last_attempt_at=attempt_at,
                last_error='subscription returned a suspiciously small key set; automatic pool replacement blocked',
            )
            write_log(
                f'Subscription auto refresh for {proto} blocked destructive shrink: '
                f'fetched={len(selected_keys)}, previous={len(previous_managed_keys)}'
            )
            return False

        _pools, added_keys, removed_keys, managed_keys, retained_keys = add_keys_to_pool(
            proto,
            fetched,
            sync_subscription=True,
            previous_managed_keys=previous_managed_keys,
        )
        update_record(
            proto,
            url=url,
            hwid_enabled=True,
            last_attempt_at=attempt_at,
            last_success_at=float(time_provider()),
            last_error='',
            managed_keys=managed_keys,
        )
        write_log(
            f'Subscription {source} refresh for {proto}: added={len(added_keys)}, '
            f'removed={len(removed_keys)}, retained_active={len(retained_keys)}, total={len(managed_keys)}'
        )
        return True
    except Exception as exc:
        update_record(
            proto,
            url=url,
            hwid_enabled=True,
            last_attempt_at=attempt_at,
            last_error=str(exc),
        )
        write_log(f'Subscription {source} refresh for {proto} failed: {exc}')
        return False
