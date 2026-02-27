#!/usr/bin/env python3
"""Legacy compatibility wrapper.

Canonical runtime entrypoint moved to:
  src/fwlab_receiver.py
"""

import runpy
from pathlib import Path


if __name__ == '__main__':
    target = Path(__file__).resolve().with_name('fwlab_receiver.py')
    runpy.run_path(str(target), run_name='__main__')
