"""Narrow, data-only publication gate for the project's generated PNG figures."""
import hashlib
from io import BytesIO
from PIL import Image

PREFIXES=('docs/figures/matched-model-', 'docs/figures/matched-p4-',
          'docs/figures/supra-', 'docs/figures/tinybrainbot-', 'docs/figures/int4-')
SPECIAL={'docs/figures/research-overview-2026-10-30.png':(1600,1710),
         'docs/figures/llm-erkenntnisse-2026-10-29.png':(1520,1400)}


def write_figure(output, dest, raw, source, lineage):
    if (not dest.startswith(PREFIXES) and dest not in SPECIAL) or not dest.endswith('.png') or '..' in dest.split('/'):
        raise ValueError('Unexpected binary asset')
    with Image.open(BytesIO(raw)) as im:
        assert im.format == 'PNG'
        assert im.size==SPECIAL[dest] if dest in SPECIAL else im.width==1600 and 1000<=im.height<=1600
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
