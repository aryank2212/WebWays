"""WebWays.exe entry point (PyInstaller).

    WebWays.exe                          start the app and open it in your browser (what double-click does)
    WebWays.exe serve [--port N] ...     start the daemon without opening a browser
    WebWays.exe token                    print the local API token
    WebWays.exe indexer serve --db index.db [...]    run an index node (see docs/operators.md)
    WebWays.exe --version

This glue lives here, not in webways_core, so the GPL client doesn't import the AGPL indexer.
"""
from __future__ import annotations

import sys


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "indexer":
        from webways_indexer.cli import main as indexer_main
        indexer_main(argv[1:])
    elif argv and argv[0] in ("serve", "token", "--version", "-h", "--help"):
        from webways_core.cli import main as core_main
        core_main(argv)
    else:
        from webways_core.cli import app_main
        app_main()


if __name__ == "__main__":
    main()
