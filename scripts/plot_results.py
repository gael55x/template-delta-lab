#!/usr/bin/env python3
"""Render result figures from verified, committed artifacts.

Usage: python3 scripts/plot_results.py [--out DIR]   (default docs/figures; DIR must be empty or absent)
matplotlib is an optional figure dependency; the benchmark and verifier use only the stdlib.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import verify_results  # noqa: E402

RUNS = {'matched': ROOT / 'results/poc', 'wrong': ROOT / 'results/poc-wrong-template'}
FAMILIES = ('sparse', 'heavy', 'random')
METHODS = ('raw', 'zlib', 'dedup_zlib', 'delta', 'min_page')
COLORS = ('#7f7f7f', '#0072B2', '#56B4E9', '#E69F00', '#009E73')  # Okabe-Ito, colorblind-safe
CHARGE = 262144
SEEDS = range(10)
NOTE = 'Synthetic page corpora, n=10 seeds per family. Bar = median; whisker = min-max across seeds (not a CI).'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(directory):
    """Repeat-0 byte totals (the verifier proves repeats agree) and raw bytes per family and seed."""
    totals, raw = {}, {}
    for r in verify_results.rows(directory / 'raw.csv'):
        if r['repeat'] == '0':
            totals[r['family'], int(r['seed']), r['method']] = int(r['total_bytes'])
            raw[r['family'], int(r['seed'])] = int(r['raw_bytes'])
    return totals, raw


def spread(values):
    values = list(values)
    return statistics.median(values), min(values), max(values)


def saving(run, family, method):
    totals, raw = run
    return spread(100 * (raw[family, s] - totals[family, s, method]) / raw[family, s] for s in SEEDS)


def paired(run, family, charge):
    totals, raw = run
    return spread(100 * (totals[family, s, 'min_page'] + charge
                         - min(totals[family, s, 'zlib'], totals[family, s, 'dedup_zlib'])) / raw[family, s]
                  for s in SEEDS)


def figure(plt, title, subtitle, ylabel, series):
    """series: (label, family -> (median, min, max), color, hatch)."""
    fig, ax = plt.subplots(figsize=(10, 6), layout='constrained')
    fig.suptitle(title, x=0.01, ha='left', fontweight='bold')
    ax.set_title(subtitle, loc='left', fontsize=7.5, color='0.3')
    width = 0.8 / len(series)
    for i, (label, stat, color, hatch) in enumerate(series):
        stats = [stat(f) for f in FAMILIES]
        x = [j + (i - (len(series) - 1) / 2) * width for j in range(len(FAMILIES))]
        med = [m for m, _, _ in stats]
        err = [[m - lo for m, lo, _ in stats], [hi - m for m, _, hi in stats]]
        bars = ax.bar(x, med, width, yerr=err, capsize=2, label=label, color=color, hatch=hatch,
                      edgecolor='black', linewidth=0.4, error_kw={'elinewidth': 0.8})
        ax.bar_label(bars, fmt='%.1f', fontsize=6.5, padding=2)
    ax.axhline(0, color='black', linewidth=0.8)
    ax.set_xticks(range(len(FAMILIES)), FAMILIES)
    ax.set_ylabel(ylabel)
    ax.grid(axis='y', alpha=0.3)
    ax.set_axisbelow(True)
    ax.legend(fontsize=7, frameon=False)
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, default=ROOT / 'docs/figures')
    out = parser.parse_args().out.resolve()
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        sys.exit(f'refusing to overwrite: {out} exists and is not an empty directory')
    try:
        report = verify_results.verify(RUNS['matched'], RUNS['wrong'])
    except (verify_results.VerificationError, KeyError, ValueError, OSError) as e:
        sys.exit(f'committed artifacts failed verification, not plotting: {e!r}')
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        sys.exit('figures need the optional matplotlib dependency (the benchmark does not)')
    matplotlib.rcParams.update({'svg.hashsalt': 'template-delta-lab', 'font.size': 9, 'hatch.linewidth': 0.5})
    matched, wrong = load(RUNS['matched']), load(RUNS['wrong'])
    figs = {
        'method-savings': figure(
            plt, 'Saving vs raw bytes by method (matched template)',
            NOTE + '\nTemplate pages shared-resident (uncharged). Below zero = encoded larger than raw.',
            'saving, % of raw bytes',
            [(m, lambda f, m=m: saving(matched, f, m), c, '') for m, c in zip(METHODS, COLORS)]),
        'paired-min-page': figure(
            plt, 'Paired per seed: min_page minus best of zlib / dedup_zlib',
            NOTE + '\nBelow zero = min_page smaller. Charged adds the 262,144 B template (64 x 4 KiB) once per family '
                   'and seed.\nWrong template = control where each page is paired with a mismatched template.',
            'min_page - best(zlib, dedup_zlib), % of raw bytes',
            [('matched template, shared', lambda f: paired(matched, f, 0), '#0072B2', ''),
             ('matched template, charged', lambda f: paired(matched, f, CHARGE), '#E69F00', ''),
             ('wrong template, shared', lambda f: paired(wrong, f, 0), '#0072B2', '//'),
             ('wrong template, charged', lambda f: paired(wrong, f, CHARGE), '#E69F00', '//')]),
    }
    out.mkdir(parents=True, exist_ok=True)
    outputs = {}
    for stem, fig in figs.items():
        for ext, meta in (('png', {'Software': None}), ('svg', {'Date': None})):
            path = out / f'{stem}.{ext}'
            fig.savefig(path, dpi=200, bbox_inches='tight', metadata=meta)
            outputs[path.name] = sha256(path)
        plt.close(fig)
    manifest = {
        'project': 'template-delta-lab',
        'generator': {'path': 'scripts/plot_results.py', 'sha256': sha256(Path(__file__).resolve())},
        'verifier': {'path': 'verify_results.py', 'sha256': sha256(ROOT / 'verify_results.py'),
                     'status': report['status']},
        'sources': {p.relative_to(ROOT).as_posix() + '/raw.csv': sha256(p / 'raw.csv') for p in RUNS.values()},
        'statistics': 'median and min-max over seeds 0-9 of repeat-0 byte totals; denominator raw_bytes',
        'matplotlib': matplotlib.__version__,
        'outputs': outputs,
    }
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'out': str(out), 'outputs': outputs}, indent=2))


if __name__ == '__main__':
    main()
