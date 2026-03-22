# pcg_entry.py
# PyInstaller entrypoint — absolute imports only.
import os
import sys

# When frozen by PyInstaller, sys._MEIPASS is the temp extraction dir.
# Add it to sys.path so the bundled package is importable.
if getattr(sys, "frozen", False):
    bundle_dir = sys._MEIPASS
    sys.path.insert(0, bundle_dir)

    # If the process is intended to be a FalkorDB worker spawned by the CLI,
    # run the worker instead of the main app.
    if os.getenv("PCG_RUN_FALKOR_WORKER") == "true":
        from platform_context_graph.core.falkor_worker import run_worker

        run_worker()
        sys.exit(0)

from platform_context_graph.cli.main import app

if __name__ == "__main__":
    app()
