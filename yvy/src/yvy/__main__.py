"""Entry point: ``python -m yvy``.

Delegatea al CLI en ``yvy.cli.__main__``.
"""
import sys
from yvy.cli.__main__ import main

sys.exit(main())
