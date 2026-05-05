"""Tests for NodeOrigin dataclass."""

from src.domain.imports.node_origin import NodeOrigin


class TestNodeOrigin:
    def test_frozen(self):
        origin = NodeOrigin(module="mod_a", imported=True, depth=2)
        try:
            origin.module = "mod_b"
            assert False, "Should raise FrozenInstanceError"
        except AttributeError:
            pass

    def test_is_local(self):
        origin = NodeOrigin(module="mod_a", imported=False, depth=0)
        assert origin.is_local()

    def test_is_not_local_when_imported(self):
        origin = NodeOrigin(module="mod_a", imported=True, depth=1)
        assert not origin.is_local()

    def test_is_direct_import(self):
        origin = NodeOrigin(module="mod_a", imported=True, depth=1)
        assert origin.is_direct_import()

    def test_is_not_direct_import_depth_2(self):
        origin = NodeOrigin(module="mod_a", imported=True, depth=2)
        assert not origin.is_direct_import()

    def test_is_not_direct_import_when_local(self):
        origin = NodeOrigin(module="mod_a", imported=False, depth=0)
        assert not origin.is_direct_import()

    def test_equality(self):
        a = NodeOrigin(module="mod_a", imported=True, depth=1)
        b = NodeOrigin(module="mod_a", imported=True, depth=1)
        assert a == b

    def test_hash(self):
        a = NodeOrigin(module="mod_a", imported=True, depth=1)
        b = NodeOrigin(module="mod_a", imported=True, depth=1)
        assert hash(a) == hash(b)
        assert len({a, b}) == 1
