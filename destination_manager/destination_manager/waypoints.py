"""Waypoint parsing independent of ROS."""
import math
from pathlib import Path

import yaml


def normalize_name(name):
    return name.strip().casefold()


def load_waypoints(filename):
    with Path(filename).expanduser().open(encoding='utf-8') as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict):
        raise ValueError('Waypoint file must be a YAML mapping')
    frame = data.get('frame_id', 'map')
    if not isinstance(frame, str) or not frame.strip():
        raise ValueError('frame_id must be a nonempty string')
    entries = data.get('destinations')
    if not isinstance(entries, dict):
        raise ValueError('destinations must be a mapping (use {} for an empty list)')
    waypoints = {}
    for name, pose in entries.items():
        if not isinstance(name, str) or not normalize_name(name):
            raise ValueError('Destination names must be nonempty strings')
        key = normalize_name(name)
        if key in waypoints:
            raise ValueError(f'Duplicate normalized destination: {key}')
        if not isinstance(pose, dict):
            raise ValueError(f'{key}: pose must be a mapping')
        values = []
        for field in ('x', 'y', 'yaw'):
            value = pose.get(field)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value)):
                raise ValueError(f'{key}.{field} must be a finite number')
            values.append(float(value))
        waypoints[key] = tuple(values)
    return frame.strip(), waypoints
