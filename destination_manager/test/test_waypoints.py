import pytest

from destination_manager.waypoints import load_waypoints


def test_load_and_normalize(tmp_path):
    file = tmp_path / 'points.yaml'
    file.write_text('frame_id: map\ndestinations:\n  " LAB ": {x: 1, y: -2, yaw: 1.57}\n')
    frame, points = load_waypoints(file)
    assert frame == 'map'
    assert points == {'lab': (1.0, -2.0, 1.57)}


@pytest.mark.parametrize('value', ['.nan', '.inf', 'true', '"1.0"', 'null'])
def test_reject_invalid_coordinates(tmp_path, value):
    file = tmp_path / 'points.yaml'
    file.write_text(f'destinations:\n  lab: {{x: {value}, y: 0, yaw: 0}}\n')
    with pytest.raises(ValueError):
        load_waypoints(file)


def test_reject_duplicate_normalized_names(tmp_path):
    file = tmp_path / 'points.yaml'
    file.write_text('destinations:\n  Lab: {x: 0, y: 0, yaw: 0}\n'
                    '  lab: {x: 1, y: 1, yaw: 0}\n')
    with pytest.raises(ValueError, match='Duplicate'):
        load_waypoints(file)


def test_empty_config(tmp_path):
    file = tmp_path / 'points.yaml'
    file.write_text('destinations: {}\n')
    assert load_waypoints(file) == ('map', {})
