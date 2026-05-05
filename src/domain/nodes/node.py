"""
Node Base Class.
Abstract base class for all rule nodes in INFERRA analysis.
Implements access levels and strong typing where appropriate.
"""

import json
import re
import abc
import hashlib
import warnings
from abc import ABCMeta
from typing import Any, Optional
from src.domain.fact_values import FactValueType
from src.domain.nodes.line_type import LineType
from src.domain.nodes import node_id_utils
from src.domain.tokens import Token, TokenStringDictionary
from src.domain.fact_values import FactValue
from src.domain.nodes.meta_data import MetaData
from src.shared.loggers import Logger

# Protected Module-Level Logger (Access Level: Protected)
_logger: Logger = Logger.get_logger(__name__)


class Node(metaclass=ABCMeta):
    """
    Abstract base class for all rule nodes.
    Implements private state with public accessors.
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Class Variables (Name Mangling)
    # -------------------------------------------------------------------------
    __static_node_id: int = 0

    # -------------------------------------------------------------------------
    # Protected Access Level: Instance Variables (Single Underscore)
    # -------------------------------------------------------------------------
    def __init__(
        self,
        id: Optional[int] = None,
        parent_text: Optional[str] = None,
        tokens: Optional[Token] = None,
        meta_data: Optional[MetaData] = None,
    ):
        """
        Public Constructor: Initializes Node.
        
        Args:
            id: Node ID
            parent_text: Text content of the node
            tokens: Tokenized representation
            meta_data: Metadata for the node
        """
        # Protected instance variables (initialized in __init__)
        self._node_unique_id: int = id if id is not None else -1
        self._node_id: Optional[int] = id
        self._stable_node_id: Optional[str] = None
        self._debug_label: Optional[str] = None
        self._source_module_name: Optional[str] = None
        self._node_name: Optional[str] = None
        self._node_line: Optional[int] = None
        self._variable_name: Optional[str] = None
        self._value: FactValue = FactValue()
        self._tokens: Token = Token()
        self._line_type: Optional[LineType] = None
        self._meta_data: Optional[MetaData] = None
        
        if parent_text is not None and tokens is not None:
            self.initialisation(parent_text, tokens)
            self._tokens = tokens
        
        if meta_data is not None:
            self._meta_data = meta_data

    # -------------------------------------------------------------------------
    # Public Access Level: Abstract Methods
    # -------------------------------------------------------------------------
    @abc.abstractmethod
    def initialisation(self, parent_text: str, tokens: Token) -> None:
        """
        Public API: Initializes the node with text and tokens.
        
        Args:
            parent_text: Text content of the node
            tokens: Tokenized representation
        """
        pass

    @abc.abstractmethod
    def get_line_type(self) -> LineType:
        """
        Public API: Returns the line type.
        
        Returns:
            LineType of the node
        """
        pass

    @abc.abstractmethod
    def self_evaluate(self, working_memory: dict) -> FactValue:
        """
        Public API: Self-evaluates the node against working memory.
        
        Args:
            working_memory: Current working memory dictionary
            
        Returns:
            FactValue result
        """
        pass

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Getters)
    # -------------------------------------------------------------------------
    def get_meta_data(self) -> Optional[MetaData]:
        """
        Public API: Returns the metadata.
        
        Returns:
            MetaData object or None
        """
        return self._meta_data

    def get_node_line(self) -> Optional[int]:
        """
        Public API: Returns the node line number.
        
        Returns:
            Line number or None
        """
        return self._node_line

    def get_node_id(self) -> Optional[int]:
        """
        Public API: Returns the runtime node ID.

        .. deprecated:: Phase 2
            Use :meth:`get_stable_node_id` or :meth:`get_node_name` instead.
            Runtime integer node IDs will be removed in Phase 3+.

        Returns:
            Node ID or None
        """
        warnings.warn(
            "Node.get_node_id() is deprecated; use get_stable_node_id() or get_node_name()",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._node_id

    def get_node_name(self) -> Optional[str]:
        """
        Public API: Returns the node name.
        
        Returns:
            Node name or None
        """
        return self._node_name

    def get_stable_node_id(self) -> Optional[str]:
        """
        Public API: Returns the canonical deterministic node ID.

        Returns:
            Stable node ID string or None
        """
        return self._stable_node_id

    def get_debug_label(self) -> Optional[str]:
        """
        Public API: Returns the human-readable debug label, if assigned.

        Returns:
            Debug label string or None
        """
        return self._debug_label

    def set_debug_label(self, debug_label: str) -> None:
        """
        Public API: Sets a human-readable debug label for this node.

        Args:
            debug_label: Label string of the form "rule_name:line_number:variable_name"
        """
        self._debug_label = debug_label

    def get_tokens(self) -> Token:
        """
        Public API: Returns the tokens.
        
        Returns:
            Token object
        """
        return self._tokens

    def get_variable_name(self) -> Optional[str]:
        """
        Public API: Returns the variable name.
        
        Returns:
            Variable name or None
        """
        return self._variable_name

    def get_fact_value(self) -> FactValue:
        """
        Public API: Returns the fact value.
        
        Returns:
            FactValue object
        """
        return self._value

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Setters)
    # -------------------------------------------------------------------------
    def set_meta_data(self, meta_data: MetaData) -> None:
        """
        Public API: Sets the metadata.
        
        Args:
            meta_data: MetaData to set
        """
        self._meta_data = meta_data

    def set_node_line(self, node_line: int) -> None:
        """
        Public API: Sets the node line number.
        
        Args:
            node_line: Line number to set
        """
        self._node_line = node_line

    def set_node_id(self, node_id: int) -> None:
        """
        Public API: Sets the runtime matrix/index node ID.

        .. deprecated:: Phase 2
            Runtime integer node IDs will be removed in Phase 3+.

        Args:
            node_id: Runtime node ID to set
        """
        warnings.warn(
            "Node.set_node_id() is deprecated; stable_id is set via refresh_stable_node_id()",
            DeprecationWarning,
            stacklevel=2,
        )
        self._node_id = node_id
        self._node_unique_id = node_id

    def set_node_variable(self, new_variable_name: str) -> None:
        """
        Public API: Sets the variable name.
        
        Args:
            new_variable_name: New variable name
        """
        self._variable_name = new_variable_name

    def refresh_stable_node_id(self, module_name: Optional[str] = None) -> str:
        """
        Public API: Recomputes the deterministic stable node ID from parse context.

        Delegates to node_id_utils.generate_node_id() so collision tracking and
        16-char ID format are applied consistently across the parse session.

        Args:
            module_name: Optional source module name override

        Returns:
            Stable node ID string
        """
        if module_name is not None:
            self._source_module_name = module_name

        rule_name = self._line_type.value if self._line_type is not None else "UNKNOWN"
        variable_name = self._variable_name or self._node_name or "__anonymous_node__"
        normalized_text = Node._normalise_identity_part(self._node_name or variable_name)
        parent_module_path = getattr(self, '_parent_module_path', '') or ''
        import_namespace = getattr(self, '_import_namespace', '') or ''

        self._stable_node_id = node_id_utils.generate_node_id(
            module_path=self._source_module_name or "__unknown_module__",
            rule_name=rule_name,
            variable_name=variable_name,
            normalized_text=normalized_text,
            parent_module_path=parent_module_path,
            import_namespace=import_namespace,
        )
        return self._stable_node_id

    def set_value(self, last_token_string: Any, last_token: Any = None) -> None:
        """
        Public API: Sets the fact value.
        
        Args:
            last_token_string: Token string
            last_token: Token object (optional)
        """
        if last_token is None:
            self._value = last_token_string
        else:
            if re.match(r"Q", last_token_string, re.IGNORECASE):
                self._value = FactValue(last_token, FactValueType.DEFI_STRING)
            elif not re.match(r"[CLMU]", last_token_string, re.IGNORECASE):
                self._value = FactValue(last_token, TokenStringDictionary.find_fact_value_type(last_token_string))
            else:
                if Node.is_boolean(last_token):
                    if re.match(r"false", last_token, re.IGNORECASE):
                        self._value = FactValue(False, FactValueType.BOOLEAN)
                    elif re.match(r"true", last_token, re.IGNORECASE):
                        self._value = FactValue(True, FactValueType.BOOLEAN)
                elif re.match(r"(^[\'\"])(.*)([\'\"]$)", last_token, re.IGNORECASE):
                    self._value = FactValue(last_token, FactValueType.DEFI_STRING)
                else:
                    self._value = FactValue(last_token, TokenStringDictionary.find_fact_value_type(last_token_string))

    # -------------------------------------------------------------------------
    # Public Access Level: Static Methods
    # -------------------------------------------------------------------------
    @staticmethod
    def is_boolean(in_string: str) -> bool:
        """
        Public API: Checks if string represents a boolean.
        
        Args:
            in_string: String to check
            
        Returns:
            True if boolean, False otherwise
        """
        if re.match(r"false+", in_string, re.IGNORECASE) or re.match(r"true+", in_string, re.IGNORECASE):
            return True
        return False

    @staticmethod
    def is_integer(in_string: str) -> bool:
        """
        Public API: Checks if string represents an integer.
        
        Args:
            in_string: String to check
            
        Returns:
            True if integer, False otherwise
        """
        return "No" == in_string

    @staticmethod
    def is_double(in_string: str) -> bool:
        """
        Public API: Checks if string represents a double.
        
        Args:
            in_string: String to check
            
        Returns:
            True if double, False otherwise
        """
        return "De" == in_string

    @staticmethod
    def is_date(in_string: str) -> bool:
        """
        Public API: Checks if string represents a date.
        
        Args:
            in_string: String to check
            
        Returns:
            True if date, False otherwise
        """
        return "Da" == in_string

    @staticmethod
    def is_url(in_string: str) -> bool:
        """
        Public API: Checks if string represents a URL.
        
        Args:
            in_string: String to check
            
        Returns:
            True if URL, False otherwise
        """
        return "Url" == in_string

    @staticmethod
    def is_hash(in_string: str) -> bool:
        """
        Public API: Checks if string represents a hash.
        
        Args:
            in_string: String to check
            
        Returns:
            True if hash, False otherwise
        """
        return "Ha" == in_string

    @staticmethod
    def is_guid(in_string: str) -> bool:
        """
        Public API: Checks if string represents a GUID.
        
        Args:
            in_string: String to check
            
        Returns:
            True if GUID, False otherwise
        """
        return "Id" == in_string

    @staticmethod
    def build_stable_node_id(
        module_name: Optional[str],
        line_type: Optional[str],
        variable_name: Optional[str],
        node_name: Optional[str],
        parent_module_path: str = "",
        import_namespace: str = "",
        node_line: Optional[int] = None,
    ) -> str:
        """
        Public API: Builds a deterministic canonical node ID.

        Args:
            module_name: Source module/rule name
            line_type: Node line type
            variable_name: Parsed variable name
            node_name: Parsed node text/name (used for normalized_text)
            parent_module_path: Parent rule/module path (empty for root nodes)
            import_namespace: Versioned package (e.g. "common_rules@2.1.0");
                empty string for local nodes
            node_line: **Deprecated** — retained for backward compatibility only.

        Returns:
            Stable SHA-256-based node ID
        """
        normalised_name = Node._normalise_identity_part(node_name or variable_name or "__anonymous_node__")
        identity_parts = [
            Node._normalise_identity_part(module_name or "__unknown_module__"),
            Node._normalise_identity_part(line_type or "UNKNOWN"),
            Node._normalise_identity_part(variable_name or node_name or "__anonymous_node__"),
            normalised_name,
            Node._normalise_identity_part(parent_module_path),
            Node._normalise_identity_part(import_namespace),
        ]
        identity_string = "|".join(identity_parts)
        return hashlib.sha256(identity_string.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalise_identity_part(value: str) -> str:
        """
        Protected Helper: Normalises identity inputs for deterministic hashing.

        Args:
            value: Raw identity input

        Returns:
            Normalised identity string
        """
        return re.sub(r"\s+", " ", str(value).strip()).lower()

    @staticmethod
    def reset() -> None:
        """
        Public API: Deprecated no-op retained for backward compatibility.
        """
        Node.__static_node_id = 0

    @staticmethod
    def get_static_node_id() -> int:
        """
        Public API: Deprecated static counter accessor retained for compatibility.
        
        Returns:
            Current static node ID
        """
        return Node.__static_node_id

    # -------------------------------------------------------------------------
    # Special Methods
    # -------------------------------------------------------------------------
    def __repr__(self) -> str:
        """
        Public API: String representation of the object.
        
        Returns:
            JSON string representation
        """
        return json.dumps(self.__dict__)
