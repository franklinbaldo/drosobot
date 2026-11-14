#!/usr/bin/env python3
"""Retrieve pinned public MaleCNS artifacts for CI only, never store in Git.

This performs NO control commands and NO access to LAN devices. Compact
connectome and port names come from the existing public FlyDoom project.
"""
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen
import argparse

ARTIFACT = 'https://raw.githubusercontent.com/franklinbaldo/franklinbaldo.github.io/main/public/flydoom/malecns_l3_compact.mcns'
CIRCUIT = 'https://raw.githubusercontent.com/franklinbaldo/franklinbaldo.github.io/main/public/flydoom/malecns_circuit.json'
ARTIFACT_SHA256 = '92a821dfbaed40fd124c9b6d9d32ee68830d2659e761c355b8340103d8d616fd'
CIRCUIT_SHA256 = '8bf1ed9f2509768472d031852bb3645bdedf8dd481beecf95c74c957f74dabae'
EXPECTED_COUNTS = {'vpl': 4589, 'vpr': 4612, 'dnl': 656, 'dnr': 648}


def fetch(url, digest, max_bytes):
    with urlopen(Request(url, headers={'User-Agent':'DrosoBot-experimental-operator/0.1'}), timeout=25) as response:
        blob = response.read(max_bytes+1)
    if len(blob)>max_bytes or hashlib.sha256(blob).hexdigest()!=digest:
        raise ValueError('External artifact size/hash mismatch; refuse run')
    return blob


def prepare(root):
    root.mkdir(parents=True, exist_ok=True)
    brain = fetch(ARTIFACT, ARTIFACT_SHA256, 8_000_000)
    annotations = fetch(CIRCUIT, CIRCUIT_SHA256, 1_000_000)
    circuit = json.loads(annotations)
    rows=[]
    for name, expected in EXPECTED_COUNTS.items():
        indices = circuit[name]
        if (len(indices)!=expected or len(set(indices))!=len(indices)
                or any(not isinstance(x,int) or isinstance(x,bool) or x<0 or x>=165122 for x in indices)):
            raise ValueError(f'Invalid port inventory: {name}')
        rows.append(name + ' ' + ' '.join(map(str,indices)))
    (root/'connectome.mcns').write_bytes(brain)
    (root/'ports.txt').write_text('\n'.join(rows)+'\n')
    (root/'provenance.json').write_text(json.dumps({
        'connectome_sha256': ARTIFACT_SHA256,
        'circuit_sha256': CIRCUIT_SHA256,
        'source_connectome': ARTIFACT,
        'source_circuit': CIRCUIT,
        'source_repository': 'franklinbaldo/franklinbaldo.github.io',
        'status':'frozen_operator_not_a_trained_controller',
        'ports':EXPECTED_COUNTS
    },sort_keys=True,indent=2)+'\n')
    print('Pinned MaleCNS artifacts verified; port count:',EXPECTED_COUNTS)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    prepare(args.output)
