"""Shared lightweight policy used by HTTP custom-service probes."""


CUSTOM_TARGET_DENY_MARKERS = (
    'unsupported_country_region_territory',
    'country, region, or territory not supported',
    'app-unavailable-in-region',
    'unavailable in region',
    'unavailable-in-region',
    'not available in your region',
    'request not allowed',
)
