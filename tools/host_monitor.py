#!/usr/bin/env python3
"""
Compatibility wrapper for host monitor sidecar.

Canonical implementation now lives at:
  sidecars/perf/monitor.py
"""

import runpy
from pathlib import Path


def main():
    target = Path(__file__).resolve().parents[1] / 'sidecars' / 'perf' / 'monitor.py'
    runpy.run_path(str(target), run_name='__main__')


if __name__ == '__main__':
    main()
