import pytest


@pytest.fixture
def app_dir(tmp_path, monkeypatch):
    """Point settings.py's and field_map_store.py's get_app_dir() at an isolated
    tmp_path, so tests never read or write the real settings.json/field_map.json
    next to this project."""
    monkeypatch.setattr('settings.get_app_dir', lambda: tmp_path)
    monkeypatch.setattr('field_map_store.get_app_dir', lambda: tmp_path)
    return tmp_path
