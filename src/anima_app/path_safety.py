from __future__ import annotations

import stat
from pathlib import Path


def path_is_link(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if is_junction is not None and is_junction():
            return True
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        attributes = getattr(path.lstat(), "st_file_attributes", 0) if reparse_flag else 0
        return bool(attributes & reparse_flag)
    except FileNotFoundError:
        return False
    except OSError:
        return True
