"""Offline community presets; RF choices are not equipment certification.

Source: MeshCore config API, retrieved 2026-11-18. Japan uses the community
920.800/SF12/BW125/CR8 proposal, not a preset in that API.
Scotland follows the ScotMesh wiki (2026-11-20). See docs/radio.md.
"""
PRESETS = {
    'US': dict(frequency=910525000, bandwidth=62500, spreading_factor=7, coding_rate=5, tx_power=20),
    # Keep the legacy EU default for existing installations.
    'EU': dict(frequency=869618000, bandwidth=62500, spreading_factor=8, coding_rate=5, tx_power=14),
    'JP': dict(frequency=920800000, bandwidth=125000, spreading_factor=12, coding_rate=8, tx_power=13),
    'CA': dict(frequency=910525000, bandwidth=62500, spreading_factor=7, coding_rate=5, tx_power=20),
    'AU': dict(frequency=916575000, bandwidth=62500, spreading_factor=7, coding_rate=7, tx_power=20),
    'NZ': dict(frequency=917375000, bandwidth=62500, spreading_factor=7, coding_rate=5, tx_power=20),
    'UK': dict(frequency=869618000, bandwidth=62500, spreading_factor=8, coding_rate=8, tx_power=14),
    'CH': dict(frequency=869618000, bandwidth=62500, spreading_factor=8, coding_rate=8, tx_power=14),
    'CZ': dict(frequency=869432000, bandwidth=62500, spreading_factor=7, coding_rate=5, tx_power=14),
    'NL': dict(frequency=869618000, bandwidth=62500, spreading_factor=7, coding_rate=5, tx_power=14),
    'PT': dict(frequency=869618000, bandwidth=62500, spreading_factor=7, coding_rate=6, tx_power=14),
    'TH': dict(frequency=921000000, bandwidth=62500, spreading_factor=7, coding_rate=5, tx_power=13),
    'VN': dict(frequency=920250000, bandwidth=62500, spreading_factor=8, coding_rate=5, tx_power=13),
    'SK': dict(frequency=869618000, bandwidth=62500, spreading_factor=7, coding_rate=5, tx_power=14),
    'SCO': dict(frequency=869618000, bandwidth=62500, spreading_factor=8, coding_rate=8, tx_power=14),
}
NAMES = {'US':'USA', 'EU':'Europe (legacy)', 'JP':'Japan', 'CA':'Canada',
         'AU':'Australia', 'NZ':'New Zealand', 'UK':'EU / UK', 'CH':'Switzerland',
         'CZ':'Czechia', 'NL':'Netherlands', 'PT':'Portugal', 'TH':'Thailand', 'VN':'Vietnam', 'SK':'Slovakia', 'SCO':'Scotland · ScotMesh'}
PATH_BYTES = {'CA':3, 'AU':2, 'NZ':2, 'CZ':2, 'SK':2, 'SCO':3}
DEFAULT_SCOPES = {'SCO':'sco'}
EUROPE = {'EU','UK','CH','CZ','NL','PT','SK','SCO'}

def normalize_scope(value):
    import re
    value=value.strip().lower().lstrip('#')
    if value and not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,29}',value):
        raise ValueError('Use 1–30 letters, numbers, _ or -')
    return value


def protocol_config(store, region=None):
    """Per-profile overrides; missing scope inherits preset, empty is unscoped."""
    region=region or store.get('region','US')
    if region not in PRESETS:raise ValueError('Unknown radio region')
    scope=store.get('scope_'+region,DEFAULT_SCOPES.get(region,'')) if store else DEFAULT_SCOPES.get(region,'')
    scope=normalize_scope(scope)
    size=int(store.get('path_bytes_'+region,PATH_BYTES.get(region,1))) if store else PATH_BYTES.get(region,1)
    if size not in (1,2,3):raise ValueError('Path hash must be 1, 2 or 3 bytes')
    return scope,size


def active_scope(store,backend=None):
    """Display the live engine scope while saved changes await a restart."""
    engine=getattr(backend,'engine',None)
    if engine and callable(getattr(engine,'get_default_flood_scope',None)):
        current=engine.get_default_flood_scope()
        return current[0] if current else ''
    return protocol_config(store)[0]


def configure_protocol(engine, region, store=None):
    """Apply path encoding and default scope before any startup advert."""
    from openhop_core.protocol.transport_keys import get_auto_key_for
    scope,size=protocol_config(store,region)
    engine.set_path_hash_mode(size-1)
    engine.set_default_flood_scope(scope,get_auto_key_for(scope) if scope else None)
