"""Reuse existing pure pytest tools; no package installation or backend execution."""
import os
import sys
import runpy

os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
sys.path.insert(0, "/mnt/c/Users/15492/AppData/Local/Programs/Python/Python313/Lib/site-packages")
sys.argv = ["pytest", "-q", "tests/test_opend_staging_window.py", "--basetemp", "output/169-staging-window/native-temp"]
runpy.run_module("pytest", run_name="__main__")
