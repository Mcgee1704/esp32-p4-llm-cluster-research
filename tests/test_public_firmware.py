import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
from public_firmware_checks import verify_keyless_config, verify_no_markers


class PublicFirmwareTests(unittest.TestCase):
    def test_empty_key_and_path_hiding_are_required(self):
        good = 'CONFIG_CLUSTER_KEY=""\nCONFIG_APP_REPRODUCIBLE_BUILD=y\nCONFIG_COMPILER_HIDE_PATHS_MACROS=y\n'
        verify_keyless_config(good)
        with self.assertRaises(ValueError):
            verify_keyless_config(good.replace('CONFIG_CLUSTER_KEY=""', 'CONFIG_CLUSTER_KEY="' + 'A' * 48 + '"'))
        with self.assertRaises(ValueError):
            verify_keyless_config(good.replace('CONFIG_APP_REPRODUCIBLE_BUILD=y', '# disabled'))

    def test_secret_and_identity_markers_are_rejected_without_echo(self):
        verify_no_markers(b'public firmware', [b'synthetic-private-key'])
        with self.assertRaisesRegex(ValueError, '^Private marker found in firmware artifact$'):
            verify_no_markers(b'header synthetic-private-key footer', [b'synthetic-private-key'])

    def test_empty_marker_cannot_disable_the_check(self):
        with self.assertRaises(ValueError):
            verify_no_markers(b'firmware', [b''])


if __name__ == '__main__':
    unittest.main()
