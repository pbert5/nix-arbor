from __future__ import annotations

import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

try:
    import fuse  # noqa: F401
except ModuleNotFoundError:
    fuse = types.ModuleType("fuse")

    class FuseOSError(OSError):
        def __init__(self, errnum: int) -> None:
            super().__init__(errnum)
            self.errno = errnum

    class Operations:
        pass

    fuse.FUSE = object
    fuse.FuseOSError = FuseOSError
    fuse.Operations = Operations
    sys.modules["fuse"] = fuse
