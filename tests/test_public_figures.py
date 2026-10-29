import io
import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace

from PIL import Image, PngImagePlugin
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
from public_figure import write_figure


class PublicationFigureTests(unittest.TestCase):
    def builder(self, folder):
        b = SimpleNamespace(output=pathlib.Path(folder), lineage={})
        b.figure = lambda dest, raw, source: write_figure(b.output, dest, raw, source, b.lineage)
        return b

    def png(self, **options):
        raw = io.BytesIO()
        Image.new('RGB', (1600, 1100), 'white').save(raw, 'PNG', **options)
        return raw.getvalue()

    def test_generated_pixels_and_provenance_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            b = self.builder(folder)
            raw = self.png()
            path = 'docs/figures/matched-model-test.png'
            b.figure(path, raw, 'test-source')
            self.assertEqual((b.output / path).read_bytes(), raw)
            self.assertEqual(b.lineage[path]['original_sha256'], b.lineage[path]['published_sha256'])

    def test_text_metadata_is_rejected(self):
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text('PrivateNote', 'private-machine-identifier')
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(AssertionError):
                self.builder(folder).figure('docs/figures/matched-model-test.png', self.png(pnginfo=metadata), 'test')

    def test_unreviewed_profile_metadata_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(AssertionError):
                self.builder(folder).figure('docs/figures/matched-model-test.png', self.png(icc_profile=b'private-profile-data'), 'test')

    def test_arbitrary_binary_destination_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                self.builder(folder).figure('firmware/device.bin', self.png(), 'test')


if __name__ == '__main__':
    unittest.main()
