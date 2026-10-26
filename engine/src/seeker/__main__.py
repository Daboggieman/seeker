"""`python -m seeker` — run the engine (uvicorn on 0.0.0.0:8420).

The container's CMD; in Phase 1 the engine ran via a venv and the same
module entry point, so there is exactly one way to start the engine.
"""

from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run(
        "seeker.api.app:create_app",
        factory=True,
        host="0.0.0.0",  # container / Tailnet reachability; never exposed publicly
        port=8420,
    )


if __name__ == "__main__":
    main()
