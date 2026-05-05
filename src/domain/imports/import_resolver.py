"""
RuleSetImportResolver — resolves modular rule imports with DFS cycle detection.

Gated by the MODULAR_IMPORTS feature flag. Detects circular imports
synchronously, enforces MAX_IMPORT_DEPTH=100, and supports timeout-guarded
rule loading.

Usage:
    resolver = RuleSetImportResolver(rule_loader=my_load_fn)
    resolved = resolver.resolve("main_rule")
    for module_name, node_set in resolved.items():
        ...
"""

import signal
import time
from collections import deque
from typing import Callable, Dict, List, Optional, Set

import structlog

from src.domain.imports.import_matchers import extract_imports
from src.domain.imports.node_origin import NodeOrigin
from src.domain.state.feature_flags import FeatureFlags

log = structlog.get_logger()

MAX_IMPORT_DEPTH = 100

DEFAULT_LOAD_TIMEOUT_S = 10


class CircularImportError(Exception):
    """Raised when a circular import chain is detected."""

    def __init__(self, import_chain: List[str]):
        self.import_chain = import_chain
        chain_str = " → ".join(import_chain)
        super().__init__(f"Circular import detected: {chain_str}")


class ImportDepthExceededError(Exception):
    """Raised when import chain depth exceeds MAX_IMPORT_DEPTH."""

    def __init__(self, depth: int, module_name: str):
        self.depth = depth
        self.module_name = module_name
        super().__init__(
            f"Import depth {depth} exceeds MAX_IMPORT_DEPTH={MAX_IMPORT_DEPTH} "
            f"at module '{module_name}'"
        )


class RuleLoadTimeoutError(Exception):
    """Raised when rule loading exceeds the configured timeout."""

    def __init__(self, module_name: str, timeout_s: float):
        self.module_name = module_name
        self.timeout_s = timeout_s
        super().__init__(
            f"Loading rule '{module_name}' timed out after {timeout_s}s"
        )


class RuleSetImportResolver:
    """
    Resolves transitive rule imports with DFS cycle detection.

    Uses a rule_loader callable to fetch rule text by name, then extracts
    IMPORT: directives recursively. Supports:
    - Circular import detection (throws CircularImportError)
    - Depth limiting (MAX_IMPORT_DEPTH=100)
    - Timeout-guarded loading (_load_rule_with_timeout)
    - Feature flag gating (MODULAR_IMPORTS)

    Args:
        rule_loader: Callable(module_name: str) -> str that returns rule text
        feature_flags: Optional FeatureFlags snapshot (uses default if None)
        load_timeout_s: Timeout per rule load in seconds (default: 10)
    """

    def __init__(
        self,
        rule_loader: Callable[[str], str],
        feature_flags: Optional[FeatureFlags] = None,
        load_timeout_s: float = DEFAULT_LOAD_TIMEOUT_S,
    ):
        self._rule_loader = rule_loader
        self._feature_flags = feature_flags or FeatureFlags()
        self._load_timeout_s = load_timeout_s
        self._resolved_cache: Dict[str, Dict[str, NodeOrigin]] = {}

    def resolve(self, root_module: str) -> Dict[str, NodeOrigin]:
        """
        Resolve all transitive imports starting from root_module.

        Returns a dict mapping each discovered module name to its NodeOrigin.
        The root module has depth=0 and imported=False.

        Args:
            root_module: Name of the root rule module

        Returns:
            Dict of {module_name: NodeOrigin} for all discovered modules

        Raises:
            CircularImportError: If a circular import is detected
            ImportDepthExceededError: If depth exceeds MAX_IMPORT_DEPTH
        """
        if not self._feature_flags.modular_imports:
            log.debug("modular_imports_disabled", root_module=root_module)
            return {root_module: NodeOrigin(module=root_module, imported=False, depth=0)}

        self._resolved_cache.clear()
        result: Dict[str, NodeOrigin] = {
            root_module: NodeOrigin(module=root_module, imported=False, depth=0)
        }
        self._dfs_resolve(root_module, result, visited=set(), path=[])
        return result

    def get_import_chain(self, root_module: str) -> List[str]:
        """
        Get the ordered list of all import directives for a module.

        This does NOT recurse — it returns only direct imports.

        Args:
            root_module: Module name to inspect

        Returns:
            List of directly imported module names
        """
        try:
            rule_text = self._load_rule_with_timeout(root_module)
        except Exception:
            return []
        return extract_imports(rule_text)

    def _dfs_resolve(
        self,
        module_name: str,
        result: Dict[str, NodeOrigin],
        visited: Set[str],
        path: List[str],
    ) -> None:
        """
        DFS traversal resolving imports recursively.

        Args:
            module_name: Current module to resolve
            result: Accumulated result dict (module_name → NodeOrigin)
            visited: Set of already-fully-processed modules
            path: Current DFS path for cycle detection

        Raises:
            CircularImportError: If module_name is already in path
            ImportDepthExceededError: If len(path) > MAX_IMPORT_DEPTH
        """
        if module_name in visited:
            return

        current_depth = len(path)

        if current_depth > MAX_IMPORT_DEPTH:
            raise ImportDepthExceededError(current_depth, module_name)

        if module_name in path:
            raise CircularImportError(path + [module_name])

        path.append(module_name)

        try:
            rule_text = self._load_rule_with_timeout(module_name)
        except (RuleLoadTimeoutError, CircularImportError, ImportDepthExceededError):
            path.pop()
            raise
        except Exception as exc:
            log.error(
                "import_resolve_load_failed",
                module_name=module_name,
                error=str(exc),
            )
            path.pop()
            return

        imports = extract_imports(rule_text)

        for imported_name in imports:
            if imported_name not in result:
                result[imported_name] = NodeOrigin(
                    module=imported_name,
                    imported=True,
                    depth=current_depth + 1,
                )
            self._dfs_resolve(imported_name, result, visited, path)

        visited.add(module_name)
        path.pop()

        log.debug(
            "import_resolved",
            module_name=module_name,
            import_count=len(imports),
            depth=current_depth,
        )

    def _load_rule_with_timeout(self, module_name: str) -> str:
        """
        Load rule text with timeout guard.

        Uses threading-based timeout on Windows (no SIGALRM).
        Falls back to direct call if threading unavailable.

        Args:
            module_name: Name of the module to load

        Returns:
            Rule text string

        Raises:
            RuleLoadTimeoutError: If loading exceeds self._load_timeout_s
        """
        result: Optional[str] = None
        error: Optional[Exception] = None

        def _load():
            nonlocal result, error
            try:
                result = self._rule_loader(module_name)
            except Exception as exc:
                error = exc

        import threading

        thread = threading.Thread(target=_load, daemon=True)
        thread.start()
        thread.join(timeout=self._load_timeout_s)

        if thread.is_alive():
            raise RuleLoadTimeoutError(module_name, self._load_timeout_s)

        if error is not None:
            raise error

        if result is None:
            raise RuleLoadTimeoutError(module_name, self._load_timeout_s)

        return result
