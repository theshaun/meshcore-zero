"""Offline community presets; RF choices are not equipment certification.

Source: MeshCore config API, retrieved 2026-11-18. Japan uses the community
920.800/SF12/BW125/CR8 proposal, not a preset in that API. See docs/radio.md.
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
}
NAMES = {'US':'USA', 'EU':'Europe (legacy)', 'JP':'Japan', 'CA':'Canada',
         'AU':'Australia', 'NZ':'New Zealand', 'UK':'EU / UK', 'CH':'Switzerland',
         'CZ':'Czechia', 'NL':'Netherlands', 'PT':'Portugal', 'TH':'Thailand', 'VN':'Vietnam'}
PATH_BYTES = {'CA':3, 'AU':2, 'NZ':2, 'CZ':2}
EUROPE = {'EU','UK','CH','CZ','NL','PT'}

def cooldown_factor(region):
    return 99 if region in EUROPE else 9
