import json
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import Column, BigInteger, String, LargeBinary, TIMESTAMP, ForeignKey, JSON, Integer, UniqueConstraint, inspect, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.orm.exc import DetachedInstanceError
from sqlalchemy_serializer import SerializerMixin, Serializer

from .database import Base


class UserORM(Base, SerializerMixin):
    __tablename__ = 'user'
    serialize_rules = ()

    user_id = Column(BigInteger, primary_key=True)
    email = Column(String)
    password = Column(String)

    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password


class RuleORM(Base, SerializerMixin):
    __tablename__ = 'rule'
    serialize_rules = ('-related_models.rule', )

    rule_id = Column(BigInteger, primary_key=True)
    name = Column(String)
    category = Column(String)
    description = Column(String)

    rule_files = relationship('FileORM', backref='rule', lazy='dynamic')
    rule_histories = relationship('HistoryORM', backref='rule', lazy='dynamic')

    def __init__(self, rule_name: Optional[str] = None, rule_category: Optional[str] = None,
                 rule_description: Optional[str] = None):
        self.name = rule_name
        self.category = rule_category
        self.description = rule_description

    def get_latest_file(self) -> Optional['FileORM']:
        return _latest_related(
            self.rule_files,
            FileORM.created_date,
            FileORM.file_id,
        )

    def get_latest_history(self) -> Optional['HistoryORM']:
        return _latest_related(
            self.rule_histories,
            HistoryORM.created_date,
            HistoryORM.history_id,
        )


class FileORM(Base, SerializerMixin):
    __tablename__ = 'file'
    serialize_rules = ()

    file_id = Column(BigInteger, primary_key=True)
    rule_id = Column(BigInteger, ForeignKey('rule.rule_id'))
    created_date = Column(TIMESTAMP, nullable=False, default=datetime.now)
    files = Column(LargeBinary)

    def __init__(self, rule_id: Optional[int] = None, files: Optional[bytearray] = None):
        self.rule_id = rule_id
        self.files = files


class HistoryORM(Base, SerializerMixin):
    __tablename__ = 'history'
    serialize_rules = ()

    history_id = Column(BigInteger, primary_key=True)
    rule_id = Column(BigInteger, ForeignKey('rule.rule_id'))
    created_date = Column(TIMESTAMP, nullable=False, default=datetime.now)
    history = Column(JSON)

    def __init__(self, rule_id: int, history: Dict[str, Any]):
        self.rule_id = rule_id
        self.history = history


class LLMProductConfigurationORM(Base, SerializerMixin):
    __tablename__ = 'llm_product_configuration'
    serialize_rules = ()

    product_id = Column(String, primary_key=True)
    enabled = Column(Boolean, nullable=False, default=True)
    provider_id = Column(String, nullable=True)
    provider_name = Column(String, nullable=True)
    model_id = Column(String, nullable=True)
    model_name = Column(String, nullable=True)
    base_url = Column(String, nullable=True)
    api = Column(String, nullable=True)
    api_key = Column(String, nullable=True)
    allowed_operations = Column(JSON, nullable=False, default=list)
    budget = Column(JSON, nullable=False, default=dict)
    evaluation_gate_status = Column(String, nullable=False, default="pending")
    updated_by = Column(String, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.now)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.now, onupdate=datetime.now)

    def __init__(
        self,
        product_id: str,
        enabled: bool = True,
        provider_id: Optional[str] = None,
        provider_name: Optional[str] = None,
        model_id: Optional[str] = None,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        api: Optional[str] = None,
        api_key: Optional[str] = None,
        allowed_operations: Optional[list[str]] = None,
        budget: Optional[Dict[str, Any]] = None,
        evaluation_gate_status: str = "pending",
        updated_by: Optional[str] = None,
    ):
        self.product_id = product_id
        self.enabled = enabled
        self.provider_id = provider_id
        self.provider_name = provider_name
        self.model_id = model_id
        self.model_name = model_name
        self.base_url = base_url
        self.api = api
        self.api_key = api_key
        self.allowed_operations = allowed_operations or []
        self.budget = budget or {}
        self.evaluation_gate_status = evaluation_gate_status
        self.updated_by = updated_by


class AegisRuleORM(Base, SerializerMixin):
    __tablename__ = 'aegis_rule'
    serialize_rules = ('-related_models.rule', )

    rule_id = Column(BigInteger, primary_key=True)
    name = Column(String)
    category = Column(String)
    description = Column(String)
    target_node_name = Column(String)

    rule_files = relationship('AegisFileORM', backref='rule', lazy='dynamic')
    rule_histories = relationship('AegisHistoryORM', backref='rule', lazy='dynamic')

    def __init__(self, rule_name: Optional[str] = None, rule_category: Optional[str] = None,
                 rule_description: Optional[str] = None, target_node_name: Optional[str] = None):
        self.name = rule_name
        self.category = rule_category
        self.description = rule_description
        self.target_node_name = target_node_name

    def get_latest_file(self) -> Optional['AegisFileORM']:
        return _latest_related(
            self.rule_files,
            AegisFileORM.created_date,
            AegisFileORM.file_id,
        )

    def get_latest_history(self) -> Optional['AegisHistoryORM']:
        return _latest_related(
            self.rule_histories,
            AegisHistoryORM.created_date,
            AegisHistoryORM.history_id,
        )


class AegisFileORM(Base, SerializerMixin):
    __tablename__ = 'aegis_file'
    serialize_rules = ()

    file_id = Column(BigInteger, primary_key=True)
    rule_id = Column(BigInteger, ForeignKey('aegis_rule.rule_id'))
    created_date = Column(TIMESTAMP, nullable=False, default=datetime.now)
    files = Column(LargeBinary)

    def __init__(self, rule_id: Optional[int] = None, files: Optional[bytearray] = None):
        self.rule_id = rule_id
        self.files = files


class AegisHistoryORM(Base, SerializerMixin):
    __tablename__ = 'aegis_history'
    serialize_rules = ()

    history_id = Column(BigInteger, primary_key=True)
    rule_id = Column(BigInteger, ForeignKey('aegis_rule.rule_id'))
    created_date = Column(TIMESTAMP, nullable=False, default=datetime.now)
    history = Column(JSON)

    def __init__(self, rule_id: int, history: Dict[str, Any]):
        self.rule_id = rule_id
        self.history = history


class AegisWorkflowDefinitionORM(Base, SerializerMixin):
    __tablename__ = 'aegis_workflow_definition'
    serialize_rules = ('-versions.workflow_definition', )

    workflow_id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    domain = Column(String, nullable=False, default="general")
    status = Column(String, nullable=False, default="draft")
    current_version_id = Column(String, nullable=True)
    version_counter = Column(Integer, nullable=False, default=0)
    created_by = Column(String, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.now)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.now, onupdate=datetime.now)

    versions = relationship(
        'AegisWorkflowVersionORM',
        backref='workflow_definition',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )

    def __init__(
        self,
        workflow_id: str,
        title: str,
        domain: str = "general",
        status: str = "draft",
        created_by: Optional[str] = None,
    ):
        self.workflow_id = workflow_id
        self.title = title
        self.domain = domain
        self.status = status
        self.created_by = created_by


class AegisWorkflowVersionORM(Base, SerializerMixin):
    __tablename__ = 'aegis_workflow_version'
    serialize_rules = ('-workflow_definition.versions', )

    version_id = Column(String, primary_key=True)
    workflow_id = Column(String, ForeignKey('aegis_workflow_definition.workflow_id'), nullable=False)
    version_number = Column(Integer, nullable=False)
    definition_payload = Column(JSON, nullable=False)
    validation_snapshot = Column(JSON, nullable=False)
    compile_output = Column(JSON, nullable=True)
    version_hash = Column(String, nullable=False)
    graph_hash = Column(String, nullable=False)
    status = Column(String, nullable=False, default="draft")
    created_by = Column(String, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.now)

    def __init__(
        self,
        version_id: str,
        workflow_id: str,
        version_number: int,
        definition_payload: Dict[str, Any],
        validation_snapshot: Dict[str, Any],
        version_hash: str,
        graph_hash: str,
        status: str = "draft",
        compile_output: Optional[Dict[str, Any]] = None,
        created_by: Optional[str] = None,
    ):
        self.version_id = version_id
        self.workflow_id = workflow_id
        self.version_number = version_number
        self.definition_payload = definition_payload
        self.validation_snapshot = validation_snapshot
        self.version_hash = version_hash
        self.graph_hash = graph_hash
        self.status = status
        self.compile_output = compile_output
        self.created_by = created_by


class AegisWorkflowRunORM(Base, SerializerMixin):
    __tablename__ = 'aegis_workflow_run'
    serialize_rules = ('-events.workflow_run', '-snapshots.workflow_run', '-action_proposals.workflow_run')

    run_id = Column(String, primary_key=True)
    workflow_id = Column(String, nullable=False)
    workflow_version_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="running")
    actor = Column(JSON, nullable=False, default=dict)
    facts = Column(JSON, nullable=False, default=dict)
    policy_hashes = Column(JSON, nullable=False, default=dict)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.now)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.now, onupdate=datetime.now)

    action_proposals = relationship(
        'AegisActionProposalORM',
        backref='workflow_run',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )
    events = relationship(
        'AegisEventLedgerEntryORM',
        backref='workflow_run',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )
    snapshots = relationship(
        'AegisSessionSnapshotORM',
        backref='workflow_run',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )

    def __init__(
        self,
        run_id: str,
        workflow_id: str,
        workflow_version_id: Optional[str] = None,
        status: str = "running",
        actor: Optional[Dict[str, Any]] = None,
        facts: Optional[Dict[str, Any]] = None,
        policy_hashes: Optional[Dict[str, Any]] = None,
    ):
        self.run_id = run_id
        self.workflow_id = workflow_id
        self.workflow_version_id = workflow_version_id
        self.status = status
        self.actor = actor or {}
        self.facts = facts or {}
        self.policy_hashes = policy_hashes or {}


class AegisActionProposalORM(Base, SerializerMixin):
    __tablename__ = 'aegis_action_proposal'
    __table_args__ = (UniqueConstraint("run_id", "proposal_id", name="uq_aegis_action_proposal_run_id"),)
    serialize_rules = ('-workflow_run.action_proposals', )

    proposal_id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey('aegis_workflow_run.run_id'), nullable=False)
    proposal_payload = Column(JSON, nullable=False)
    actor = Column(JSON, nullable=False, default=dict)
    facts = Column(JSON, nullable=False, default=dict)
    evidence_refs = Column(JSON, nullable=False, default=list)
    policy_hashes = Column(JSON, nullable=False, default=dict)
    option_set = Column(JSON, nullable=False, default=dict)
    gate_decision = Column(JSON, nullable=False, default=dict)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.now)

    def __init__(
        self,
        proposal_id: str,
        run_id: str,
        proposal_payload: Dict[str, Any],
        actor: Optional[Dict[str, Any]] = None,
        facts: Optional[Dict[str, Any]] = None,
        evidence_refs: Optional[list[str]] = None,
        policy_hashes: Optional[Dict[str, Any]] = None,
        option_set: Optional[Dict[str, Any]] = None,
        gate_decision: Optional[Dict[str, Any]] = None,
    ):
        self.proposal_id = proposal_id
        self.run_id = run_id
        self.proposal_payload = proposal_payload
        self.actor = actor or {}
        self.facts = facts or {}
        self.evidence_refs = evidence_refs or []
        self.policy_hashes = policy_hashes or {}
        self.option_set = option_set or {}
        self.gate_decision = gate_decision or {}


class AegisEventLedgerEntryORM(Base, SerializerMixin):
    __tablename__ = 'aegis_event_ledger_entry'
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_aegis_event_run_sequence"),
        UniqueConstraint("run_id", "idempotency_key", name="uq_aegis_event_run_idempotency"),
    )
    serialize_rules = ('-workflow_run.events', )

    event_id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey('aegis_workflow_run.run_id'), nullable=False)
    sequence = Column(Integer, nullable=False)
    idempotency_key = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    actor = Column(JSON, nullable=False, default=dict)
    payload = Column(JSON, nullable=False, default=dict)
    pre_state = Column(JSON, nullable=False, default=dict)
    evidence_refs = Column(JSON, nullable=False, default=list)
    policy_hashes = Column(JSON, nullable=False, default=dict)
    option_set = Column(JSON, nullable=False, default=dict)
    approval_state = Column(JSON, nullable=False, default=dict)
    fallback_state = Column(JSON, nullable=False, default=dict)
    receipt = Column(JSON, nullable=False, default=dict)
    previous_hash = Column(String, nullable=False)
    event_hash = Column(String, nullable=False)
    correction_of_event_id = Column(String, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.now)

    def __init__(
        self,
        event_id: str,
        run_id: str,
        sequence: int,
        idempotency_key: str,
        event_type: str,
        previous_hash: str,
        event_hash: str,
        actor: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
        pre_state: Optional[Dict[str, Any]] = None,
        evidence_refs: Optional[list[str]] = None,
        policy_hashes: Optional[Dict[str, Any]] = None,
        option_set: Optional[Dict[str, Any]] = None,
        approval_state: Optional[Dict[str, Any]] = None,
        fallback_state: Optional[Dict[str, Any]] = None,
        receipt: Optional[Dict[str, Any]] = None,
        correction_of_event_id: Optional[str] = None,
    ):
        self.event_id = event_id
        self.run_id = run_id
        self.sequence = sequence
        self.idempotency_key = idempotency_key
        self.event_type = event_type
        self.actor = actor or {}
        self.payload = payload or {}
        self.pre_state = pre_state or {}
        self.evidence_refs = evidence_refs or []
        self.policy_hashes = policy_hashes or {}
        self.option_set = option_set or {}
        self.approval_state = approval_state or {}
        self.fallback_state = fallback_state or {}
        self.receipt = receipt or {}
        self.previous_hash = previous_hash
        self.event_hash = event_hash
        self.correction_of_event_id = correction_of_event_id


class AegisSessionSnapshotORM(Base, SerializerMixin):
    __tablename__ = 'aegis_session_snapshot'
    serialize_rules = ('-workflow_run.snapshots', )

    snapshot_id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey('aegis_workflow_run.run_id'), nullable=False)
    event_sequence_start = Column(Integer, nullable=False)
    event_sequence_end = Column(Integer, nullable=False)
    snapshot_hash = Column(String, nullable=False)
    proposal_hash = Column(String, nullable=False)
    evidence_hash = Column(String, nullable=False)
    policy_hash = Column(String, nullable=False)
    import_tree_hash = Column(String, nullable=True)
    option_set_hash = Column(String, nullable=False)
    approval_hash = Column(String, nullable=False)
    fallback_hash = Column(String, nullable=False)
    receipt_hash = Column(String, nullable=True)
    snapshot_payload = Column(JSON, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.now)

    def __init__(
        self,
        snapshot_id: str,
        run_id: str,
        event_sequence_start: int,
        event_sequence_end: int,
        snapshot_hash: str,
        proposal_hash: str,
        evidence_hash: str,
        policy_hash: str,
        option_set_hash: str,
        approval_hash: str,
        fallback_hash: str,
        snapshot_payload: Dict[str, Any],
        import_tree_hash: Optional[str] = None,
        receipt_hash: Optional[str] = None,
    ):
        self.snapshot_id = snapshot_id
        self.run_id = run_id
        self.event_sequence_start = event_sequence_start
        self.event_sequence_end = event_sequence_end
        self.snapshot_hash = snapshot_hash
        self.proposal_hash = proposal_hash
        self.evidence_hash = evidence_hash
        self.policy_hash = policy_hash
        self.import_tree_hash = import_tree_hash
        self.option_set_hash = option_set_hash
        self.approval_hash = approval_hash
        self.fallback_hash = fallback_hash
        self.receipt_hash = receipt_hash
        self.snapshot_payload = snapshot_payload


class AegisTriggerPolicyORM(Base, SerializerMixin):
    __tablename__ = 'aegis_trigger_policy'
    serialize_rules = ('-receipts.trigger_policy', )

    policy_id = Column(String, primary_key=True)
    version = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active")
    mode = Column(String, nullable=False)
    source_key = Column(String, nullable=False)
    target_key = Column(String, nullable=False)
    source = Column(JSON, nullable=False, default=dict)
    target = Column(JSON, nullable=False, default=dict)
    constraints = Column(JSON, nullable=False, default=dict)
    payload = Column(JSON, nullable=False, default=dict)
    policy_hash = Column(String, nullable=False)
    created_by = Column(String, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.now)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.now, onupdate=datetime.now)

    receipts = relationship(
        'AegisTriggerReceiptORM',
        backref='trigger_policy',
        lazy='dynamic',
        cascade='all, delete-orphan',
    )

    def __init__(
        self,
        policy_id: str,
        version: str,
        mode: str,
        source_key: str,
        target_key: str,
        source: Dict[str, Any],
        target: Dict[str, Any],
        constraints: Dict[str, Any],
        payload: Dict[str, Any],
        policy_hash: str,
        status: str = "active",
        created_by: Optional[str] = None,
    ):
        self.policy_id = policy_id
        self.version = version
        self.mode = mode
        self.status = status
        self.source_key = source_key
        self.target_key = target_key
        self.source = source
        self.target = target
        self.constraints = constraints
        self.payload = payload
        self.policy_hash = policy_hash
        self.created_by = created_by


class AegisTriggerReceiptORM(Base, SerializerMixin):
    __tablename__ = 'aegis_trigger_receipt'
    __table_args__ = (
        UniqueConstraint("policy_id", "idempotency_key", name="uq_aegis_trigger_receipt_policy_idempotency"),
    )
    serialize_rules = ('-trigger_policy.receipts', )

    trigger_run_id = Column(String, primary_key=True)
    policy_id = Column(String, ForeignKey('aegis_trigger_policy.policy_id'), nullable=False)
    idempotency_key = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    mode = Column(String, nullable=False)
    decision = Column(String, nullable=False)
    status = Column(String, nullable=False)
    source = Column(JSON, nullable=False, default=dict)
    target = Column(JSON, nullable=False, default=dict)
    actor = Column(JSON, nullable=False, default=dict)
    facts_passed = Column(JSON, nullable=False, default=dict)
    approval_state = Column(JSON, nullable=False, default=dict)
    execution = Column(JSON, nullable=False, default=dict)
    guardrail = Column(JSON, nullable=False, default=dict)
    correlation_id = Column(String, nullable=True)
    policy_hash = Column(String, nullable=False)
    receipt_hash = Column(String, nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.now)

    def __init__(
        self,
        trigger_run_id: str,
        policy_id: str,
        idempotency_key: str,
        event_type: str,
        mode: str,
        decision: str,
        status: str,
        source: Dict[str, Any],
        target: Dict[str, Any],
        actor: Dict[str, Any],
        facts_passed: Dict[str, Any],
        approval_state: Dict[str, Any],
        execution: Dict[str, Any],
        guardrail: Dict[str, Any],
        correlation_id: Optional[str],
        policy_hash: str,
        receipt_hash: str,
        payload: Dict[str, Any],
    ):
        self.trigger_run_id = trigger_run_id
        self.policy_id = policy_id
        self.idempotency_key = idempotency_key
        self.event_type = event_type
        self.mode = mode
        self.decision = decision
        self.status = status
        self.source = source
        self.target = target
        self.actor = actor
        self.facts_passed = facts_passed
        self.approval_state = approval_state
        self.execution = execution
        self.guardrail = guardrail
        self.correlation_id = correlation_id
        self.policy_hash = policy_hash
        self.receipt_hash = receipt_hash
        self.payload = payload


def _latest_related(collection: Any, *order_columns: Any) -> Any:
    if hasattr(collection, "order_by"):
        try:
            return collection.order_by(
                *(column.desc() for column in order_columns)
            ).first()
        except DetachedInstanceError:
            items = _detached_related_items(collection)
        else:
            items = []
    else:
        items = list(collection)

    if not items:
        return None

    return sorted(
        items,
        key=lambda item: tuple(
            _related_sort_value(item, column) for column in order_columns
        ),
    )[-1]


def _related_sort_value(item: Any, column: Any) -> Any:
    value = getattr(item, column.key, None)
    if value is not None:
        return value
    if "date" in column.key or column.key.endswith("_at"):
        return datetime.min
    return -1


def _detached_related_items(collection: Any) -> list[Any]:
    instance = getattr(collection, "instance", None)
    attr = getattr(collection, "attr", None)
    key = getattr(attr, "key", None)
    if instance is None or key is None:
        return []
    return list(inspect(instance).attrs[key].history.added)
