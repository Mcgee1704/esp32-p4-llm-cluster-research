"""Small offline admission checks for public, keyless diagnostic firmware."""
import re


def verify_keyless_config(text):
    for line in ['CONFIG_CLUSTER_KEY=""', 'CONFIG_APP_REPRODUCIBLE_BUILD=y',
                 'CONFIG_COMPILER_HIDE_PATHS_MACROS=y']:
        if not re.search(r'^' + re.escape(line) + r'\s*$', text, re.M):
            raise ValueError('Public firmware must have an empty LAN key and hidden build paths')
    keys = re.findall(r'^CONFIG_CLUSTER_KEY=(.*)$', text, re.M)
    if len(keys) != 1 or keys[0].strip() != '""':
        raise ValueError('Ambiguous or nonempty public firmware key')


def verify_no_markers(raw, markers):
    if not markers or any(not value for value in markers):
        raise ValueError('Explicit nonempty marker list required')
    if any(value.lower() in raw.lower() for value in markers):
        raise ValueError('Private marker found in firmware artifact')
