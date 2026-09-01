import pytest

import config
import field_map_store


def test_load_field_map_seeds_defaults_when_file_missing(app_dir):
    result = field_map_store.load_field_map()

    assert result == field_map_store.default_field_map()
    assert (app_dir / 'field_map.json').exists()


def test_save_then_load_round_trips_field_map(app_dir):
    data = {'yalla': [{'tag': '<x>', 'column': 'X', 'processor': None}]}

    field_map_store.save_field_map(data)

    assert field_map_store.load_field_map() == data


@pytest.mark.parametrize('corrupt_content', ['{not valid json', 'null', '[]', '{}'])
def test_load_field_map_falls_back_to_defaults_on_corrupt_or_empty_json(app_dir, corrupt_content):
    (app_dir / 'field_map.json').write_text(corrupt_content, encoding='utf-8')

    assert field_map_store.load_field_map() == field_map_store.default_field_map()


def test_default_field_map_converts_config_tuples_to_dicts():
    result = field_map_store.default_field_map()

    for profile, fields in config.FIELD_MAP.items():
        assert result[profile] == [
            {'tag': tag, 'column': col_def, 'processor': processor_key}
            for tag, col_def, processor_key in fields
        ]


def test_profile_names_matches_profile_signatures_keys():
    assert field_map_store.profile_names() == list(config.PROFILE_SIGNATURES.keys())
