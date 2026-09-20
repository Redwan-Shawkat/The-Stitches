"""PyInstaller entry point.

`python -m uninstaller` can't be the entry point for a frozen build: a
bundled script runs as __main__, not as a package member, so the package's
own relative imports have nothing to resolve against. This three-line
shim is the whole fix.
"""

from uninstaller.gui import main

raise SystemExit(main())
