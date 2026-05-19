from src.domain.nodes.meta_data import MetaData


class TestMetaDataInit:
    def test_default_init(self):
        md = MetaData()
        assert md.get_reference() is None
        assert md.get_origin() is None
        assert md.get_statement() is None

    def test_init_with_reference(self):
        md = MetaData(reference="ref1")
        assert md.get_reference() == "ref1"
        assert md.get_origin() is None
        assert md.get_statement() is None

    def test_init_with_origin(self):
        md = MetaData(origin="section1")
        assert md.get_origin() == "section1"
        assert md.get_reference() is None

    def test_init_with_statement(self):
        md = MetaData(statement="stmt1")
        assert md.get_statement() == "stmt1"
        assert md.get_reference() is None

    def test_init_with_all(self):
        md = MetaData(reference="r", origin="o", statement="s")
        assert md.get_reference() == "r"
        assert md.get_origin() == "o"
        assert md.get_statement() == "s"


class TestMetaDataSetters:
    def test_set_reference(self):
        md = MetaData()
        md.set_reference("new_ref")
        assert md.get_reference() == "new_ref"

    def test_set_origin(self):
        md = MetaData()
        md.set_origin("new_origin")
        assert md.get_origin() == "new_origin"

    def test_set_statement(self):
        md = MetaData()
        md.set_statement("new_stmt")
        assert md.get_statement() == "new_stmt"

    def test_set_reference_overwrite(self):
        md = MetaData(reference="old")
        md.set_reference("new")
        assert md.get_reference() == "new"

    def test_set_origin_overwrite(self):
        md = MetaData(origin="old")
        md.set_origin("new")
        assert md.get_origin() == "new"

    def test_set_statement_overwrite(self):
        md = MetaData(statement="old")
        md.set_statement("new")
        assert md.get_statement() == "new"


class TestMetaDataInstantiateAttrs:
    def test_instantiate_reference(self):
        md = MetaData()
        md.instantiate_attrs("# Reference: some ref value")
        assert md.get_reference() == "some ref value"

    def test_instantiate_origin(self):
        md = MetaData()
        md.instantiate_attrs("# Section: some section")
        assert md.get_origin() == "some section"

    def test_instantiate_statement(self):
        md = MetaData()
        md.instantiate_attrs("# Original: some original statement")
        assert md.get_statement() == "some original statement"

    def test_instantiate_reference_without_colon(self):
        md = MetaData()
        md.instantiate_attrs("# Reference some ref")
        assert md.get_reference() == "some ref"

    def test_instantiate_no_match(self):
        md = MetaData()
        md.instantiate_attrs("some random line")
        assert md.get_reference() is None
        assert md.get_origin() is None
        assert md.get_statement() is None

    def test_instantiate_reference_preserves_existing_others(self):
        md = MetaData(reference="keep_me")
        md.instantiate_attrs("# Section: my section")
        assert md.get_reference() == "keep_me"
        assert md.get_origin() == "my section"


class TestIsMetaData:
    def test_is_meta_data_reference(self):
        assert MetaData.is_meta_data("# Reference: val") is True

    def test_is_meta_data_section(self):
        assert MetaData.is_meta_data("# Section: val") is True

    def test_is_meta_data_original(self):
        assert MetaData.is_meta_data("# Original: val") is True

    def test_is_meta_data_false(self):
        assert MetaData.is_meta_data("just a normal line") is False

    def test_is_meta_data_empty(self):
        assert MetaData.is_meta_data("") is False

    def test_is_meta_data_partial_no_hash(self):
        assert MetaData.is_meta_data("Reference: val") is False
