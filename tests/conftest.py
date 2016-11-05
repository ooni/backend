import os
import pytest

from measurements.app import create_app

def pytest_collection_modifyitems(items):
    for item in items:
        module_dir = os.path.dirname(item.location[0])
        if module_dir.endswith("functional"):
            item.add_marker(pytest.mark.functional)
        elif module_dir.endswith("unit"):
            item.add_marker(pytest.mark.unit)

@pytest.yield_fixture(scope='session')
def app():
    app = create_app()
    ctx = app.app_context()
    ctx.push()

    yield app

    ctx.pop()

@pytest.fixture(scope='session')
def client(app):
    return app.test_client()
