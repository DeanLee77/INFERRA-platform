import pytest
from src.domain.nodes.dependency_matrix import DependencyMatrix
from src.domain.nodes.dependency_type import DependencyType


@pytest.fixture
def sample_matrix():
    matrix_2d = [
        [-1, DependencyType.get_and(), DependencyType.get_or()],
        [DependencyType.get_and(), -1, DependencyType.get_mandatory()],
        [DependencyType.get_or(), DependencyType.get_mandatory(), -1],
    ]
    return DependencyMatrix(matrix_2d)


@pytest.fixture
def empty_matrix():
    return DependencyMatrix()


class TestDependencyMatrixInit:
    def test_init_with_data(self):
        matrix_2d = [[-1, 8], [8, -1]]
        dm = DependencyMatrix(matrix_2d)
        assert dm.get_dependency_two_dimension_list() == matrix_2d

    def test_init_empty(self):
        dm = DependencyMatrix()
        assert dm.get_dependency_two_dimension_list() == []


class TestGetDependencyType:
    def test_get_dependency_type_valid(self, sample_matrix):
        dep_type = sample_matrix.get_dependency_type(0, 1)
        assert dep_type == DependencyType.get_and()

    def test_get_dependency_type_negative_parent(self, sample_matrix):
        with pytest.raises(IndexError):
            sample_matrix.get_dependency_type(-1, 0)

    def test_get_dependency_type_negative_child(self, sample_matrix):
        with pytest.raises(IndexError):
            sample_matrix.get_dependency_type(0, -1)


class TestGetToChildDependencyList:
    def test_get_children_of_node_0(self, sample_matrix):
        children = sample_matrix.get_to_child_dependency_list(0)
        assert 1 in children
        assert 2 in children

    def test_get_children_of_node_1(self, sample_matrix):
        children = sample_matrix.get_to_child_dependency_list(1)
        assert 0 in children
        assert 2 in children

    def test_get_children_negative_id(self, sample_matrix):
        with pytest.raises(IndexError):
            sample_matrix.get_to_child_dependency_list(-1)

    def test_get_children_out_of_range(self, sample_matrix):
        with pytest.raises(IndexError):
            sample_matrix.get_to_child_dependency_list(99)

    def test_get_children_empty_matrix(self, empty_matrix):
        with pytest.raises(IndexError):
            empty_matrix.get_to_child_dependency_list(0)


class TestGetOrToChildDependencyList:
    def test_get_or_children(self, sample_matrix):
        or_children = sample_matrix.get_or_to_child_dependency_list(0)
        assert 2 in or_children

    def test_get_or_children_negative_id(self, sample_matrix):
        with pytest.raises(IndexError):
            sample_matrix.get_or_to_child_dependency_list(-1)

    def test_get_or_children_out_of_range(self, sample_matrix):
        with pytest.raises(IndexError):
            sample_matrix.get_or_to_child_dependency_list(99)


class TestGetAndToChildDependencyList:
    def test_get_and_children(self, sample_matrix):
        and_children = sample_matrix.get_and_to_child_dependency_list(0)
        assert 1 in and_children

    def test_get_and_children_negative_id(self, sample_matrix):
        with pytest.raises(IndexError):
            sample_matrix.get_and_to_child_dependency_list(-1)

    def test_get_and_children_out_of_range(self, sample_matrix):
        with pytest.raises(IndexError):
            sample_matrix.get_and_to_child_dependency_list(99)


class TestGetMandatoryToChildDependencyList:
    def test_get_mandatory_children(self, sample_matrix):
        mandatory_children = sample_matrix.get_mandatory_to_child_dependency_list(1)
        assert 2 in mandatory_children

    def test_get_mandatory_children_negative_id(self, sample_matrix):
        with pytest.raises(IndexError):
            sample_matrix.get_mandatory_to_child_dependency_list(-1)

    def test_get_mandatory_children_out_of_range(self, sample_matrix):
        with pytest.raises(IndexError):
            sample_matrix.get_mandatory_to_child_dependency_list(99)


class TestGetFromParentDependencyList:
    def test_get_parents_of_node_2(self, sample_matrix):
        parents = sample_matrix.get_from_parent_dependency_list(2)
        assert 0 in parents
        assert 1 in parents

    def test_get_parents_negative_id(self, sample_matrix):
        with pytest.raises(IndexError):
            sample_matrix.get_from_parent_dependency_list(-1)

    def test_get_parents_out_of_range(self, sample_matrix):
        with pytest.raises(IndexError):
            sample_matrix.get_from_parent_dependency_list(99)


class TestHasMandatoryChildNode:
    def test_has_mandatory_child_true(self, sample_matrix):
        assert sample_matrix.has_mandatory_child_node(1) is True

    def test_has_mandatory_child_false(self, sample_matrix):
        assert sample_matrix.has_mandatory_child_node(0) is False


class TestSparseItems:
    def test_sparse_items_yields_non_neg1(self, sample_matrix):
        items = list(sample_matrix.sparse_items())
        assert len(items) > 0
        for (pid, cid), dep_type in items:
            assert dep_type != -1
            assert pid != cid

    def test_sparse_items_empty_matrix(self, empty_matrix):
        items = list(empty_matrix.sparse_items())
        assert items == []

    def test_sparse_items_excludes_self_refs(self):
        matrix_2d = [[-1]]
        dm = DependencyMatrix(matrix_2d)
        items = list(dm.sparse_items())
        assert items == []


class TestRepr:
    def test_repr_returns_string(self, sample_matrix):
        result = repr(sample_matrix)
        assert isinstance(result, str)

    def test_repr_contains_json(self, sample_matrix):
        result = repr(sample_matrix)
        assert "dependency_two_dimension_list" in result or "_DependencyMatrix__dependency_two_dimension_list" in result
