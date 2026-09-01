import json

import pytest

import settings


def test_load_settings_creates_defaults_when_file_missing(app_dir):
    result = settings.load_settings()

    assert result == settings.DEFAULT_SETTINGS
    assert (app_dir / 'settings.json').exists()


def test_save_then_load_round_trips_values(app_dir):
    settings.save_settings({'last_source_folder': 'C:/cards', 'last_excel_folder': 'C:/data'})

    result = settings.load_settings()

    assert result == {'last_source_folder': 'C:/cards', 'last_excel_folder': 'C:/data'}


def test_load_settings_ignores_unknown_keys(app_dir):
    (app_dir / 'settings.json').write_text(
        json.dumps({'last_source_folder': 'C:/cards', 'unexpected_key': 'value'}),
        encoding='utf-8',
    )

    result = settings.load_settings()

    assert result == {'last_source_folder': 'C:/cards', 'last_excel_folder': '.'}


@pytest.mark.parametrize('corrupt_content', ['{not valid json', 'null', '[]', '"just a string"', '42'])
def test_load_settings_falls_back_to_defaults_on_corrupt_or_non_dict_json(app_dir, corrupt_content):
    # Regression: a settings.json that is valid JSON but not an object (e.g. `null`, `[]`) used
    # to raise an uncaught AttributeError from data.items(), crashing the app at startup instead
    # of falling back to defaults as load_settings()'s own docstring promises ("never raises").
    (app_dir / 'settings.json').write_text(corrupt_content, encoding='utf-8')

    result = settings.load_settings()

    assert result == settings.DEFAULT_SETTINGS
