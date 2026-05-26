import pytest

from src.tasks.celery_app import CELERY_AVAILABLE, TASK_MODULES, app


@pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery is unavailable")
def test_celery_app_imports_async_task_modules():
    assert set(TASK_MODULES) <= set(app.conf.imports)


@pytest.mark.skipif(not CELERY_AVAILABLE, reason="Celery is unavailable")
def test_async_task_modules_register_with_inferra_app():
    import src.tasks.induction  # noqa: F401
    import src.tasks.ontology_post_reasoner  # noqa: F401
    import src.tasks.rule_sync  # noqa: F401

    expected_tasks = {
        "src.tasks.rule_sync.compile_and_push_to_fuseki",
        "src.tasks.ontology_post_reasoner._ontology_post_reasoner_task",
        "src.tasks.induction.run_induction_batch",
    }

    assert expected_tasks <= set(app.tasks.keys())
