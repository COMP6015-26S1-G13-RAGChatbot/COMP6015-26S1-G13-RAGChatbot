"""Stage pinned source PDFs and an operator-reviewable inventory. No secrets."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.request import urlopen

SOURCES = [
    ('ieee-bylaws', 'IEEE Constitution and Bylaws', 'ieee-constitution-and-bylaws.pdf', 100, True),
    ('smcs-bylaws', 'SMCS Constitution and Bylaws', 'SMC-Constitution-Bylaws-August-2023-web.pdf', 90, True),
    ('smcs-technical', 'SMCS Technical Manual', 'SMCS-Techncal-Manual-2023-08-01.pdf', 80, True),
    ('ieee-financial', 'Financial Operations Manual', 'financial-ops-manual.pdf', 80, False),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--download', action='store_true', help='Download the pinned team source PDFs instead of reading local Git objects')
    args = parser.parse_args()
    provenance = json.loads(Path(__file__).with_name('meet_engine').joinpath('provenance.json').read_text())
    ref = provenance['source_commit']
    folder = args.output.resolve()
    inventory_file = folder / 'meet_inventory.json'
    if inventory_file.exists():
        raise SystemExit('Inventory already exists; use administrator version review instead of overwriting it')
    source_dir = folder / 'sources'
    source_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for identifier, title, name, rank, enabled in SOURCES:
        path = f'Final-Testing/data/authoritative/{name}'
        if args.download:
            from urllib.parse import quote
            url = 'https://raw.githubusercontent.com/COMP6015-26S1-G13-RAGChatbot/COMP6015-26S1-G13-RAGChatbot/' + ref + '/' + quote(path)
            with urlopen(url, timeout=60) as response:
                raw = response.read(20 * 1024 * 1024 + 1)
        else:
            raw = subprocess.check_output(['git', 'show', f'{ref}:{path}'])
        if not raw.startswith(b'%PDF-') or len(raw) > 20 * 1024 * 1024:
            raise SystemExit('Source download was not an acceptable PDF')
        dest = source_dir / name
        dest.write_bytes(raw)
        rows.append({'document_id': identifier, 'title': title, 'version': 'Supplied corpus at '+ref[:8],
                     'document_type': 'constitution_bylaws' if 'bylaws' in identifier else 'manual',
                     'approval_status': 'approved', 'usage': 'production', 'retrieval_enabled': enabled,
                     'authority_level': rank, 'source_path': str(dest),
                     'content_hash': hashlib.sha256(raw).hexdigest(),
                     'source_metadata': {'source': name, 'source_type': 'authoritative',
                                         'authority_level': 4, 'authority_rank': rank}})
    inventory_file.write_text(json.dumps(rows, indent=2))
    print('Prepared', inventory_file)
    print('Review source approval and authority with the supervisor before public use. Financial extraction remains disabled.')


if __name__ == '__main__':
    main()
