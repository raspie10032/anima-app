"""Python 3.10 compatibility for the upstream string enum."""
try:
    from enum import StrEnum
except ImportError:
    from enum import Enum

    class StrEnum(str, Enum):
        def __str__(self):
            return str(self.value)
