"""Explicit module entrypoint; importing this module starts nothing."""

from qm_research_agent.runtime import main

if __name__ == "__main__":
    raise SystemExit(main())
