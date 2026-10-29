"""Narrow, data-only publication gate for the project's generated PNG figures."""
import hashlib
from io import BytesIO
from PIL import Image


def write_figure(output, dest, raw, source, lineage):
    if not dest.startswith('docs/figures/matched-model-') or not dest.endswith('.png') or '..' in dest.split('/'):
        raise ValueError('Unexpected binary asset')
    with Image.open(BytesIO(raw)) as im:
        assert im.format == 'PNG' and im.width == 1600 and 1000 <= im.height <= 1400
        im.verify()
    # Pillow's .text triggers pixel loading. Reopen after CRC verification and
    # load so metadata after image chunks is inspected too.
    with Image.open(BytesIO(raw)) as im:
        im.load()
        assert set(im.info) <= {'dpi', 'aspect'}, 'Unreviewed PNG metadata'
        assert not getattr(im, 'text', {}), 'PNG text metadata is not allowed'
    path = output / dest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    lineage[dest] = {'source': source, 'original_sha256': digest, 'published_sha256': digest}
