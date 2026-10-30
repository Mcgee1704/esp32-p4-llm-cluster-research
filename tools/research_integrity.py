"""Distinguish historical freezes from checksums of public representations."""
import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def recorded_file(path, expected, root=ROOT):
    """Check current bytes AND their explicitly recorded historical relationship.

    Public metadata never establishes that translated bytes were preregistered.
    Inference/source guards do not call this helper: fresh runs freeze new files.
    """
    path = pathlib.Path(path).resolve(); root = pathlib.Path(root).resolve()
    manifest = root / 'provenance/representations.json'
    if manifest.exists():
        key = path.relative_to(root).as_posix()
        entry = json.loads(manifest.read_text(encoding='utf-8'))['files'][key]
        if digest(path) != entry['published_sha256'] or expected != entry['historical_sha256']:
            raise ValueError('Public representation or historical reference changed: ' + key)
    elif digest(path) != expected:
        raise ValueError('Historical record changed: ' + str(path))


def protocol(data):
    data = pathlib.Path(data)
    recorded_file(data / 'protocol.json', (data / 'protocol.sha256').read_text().strip())
    return json.loads((data / 'protocol.json').read_text(encoding='utf-8'))


def data_arguments(parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--run', help='Fresh study directory identifier under the research data root')
    group.add_argument('--output', type=pathlib.Path, help='Explicit study data directory; same value for every stage')


def study_directory(args, default):
    import re
    default = pathlib.Path(default)
    if args.run:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', args.run) or args.run in ['.', '..']:
            raise ValueError('Invalid run identifier')
        return default.parent / args.run
    return args.output.resolve() if args.output else default
