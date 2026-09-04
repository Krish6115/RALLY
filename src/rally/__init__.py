"""Rally — Safe AI Revenue Recovery Decisioning."""

import sys
import importlib

__version__ = "0.1.0"

# Register module aliases for backward compatibility and case-insensitivity
sys.modules.setdefault("rally", sys.modules[__name__])
sys.modules.setdefault("Rally", sys.modules[__name__])
sys.modules.setdefault("paymentpulse", sys.modules[__name__])


class _RallyAliasFinder:
    """Import hook allowing `paymentpulse.<submod>` and `Rally.<submod>` to resolve to `rally.<submod>`."""

    @staticmethod
    def find_spec(fullname, path, target=None):
        prefix = None
        if fullname.startswith("paymentpulse."):
            prefix = "paymentpulse."
        elif fullname.startswith("Rally."):
            prefix = "Rally."

        if prefix:
            target_name = "rally." + fullname[len(prefix):]
            try:
                mod = importlib.import_module(target_name)
                sys.modules[fullname] = mod
                return importlib.util.find_spec(target_name)
            except Exception:
                return None
        return None


if not any(isinstance(finder, _RallyAliasFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _RallyAliasFinder())
