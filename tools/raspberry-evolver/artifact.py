"""Version 1 image manifest validation; this does not authenticate provenance."""
import re


def validate(data):
    if not isinstance(data, dict):
        raise ValueError('manifest must be an object')
    def matches(name, pattern):
        value = data.get(name)
        return isinstance(value, str) and re.fullmatch(pattern, value) is not None
    if (type(data.get('schema_version')) is not int or data['schema_version'] != 1
            or data.get('model') != 'Raspberry Pi 4'
            or data.get('hostname') != 'raspberry-evolver'
            or not matches('source_revision', r'[0-9a-f]{40}(?:[0-9a-f]{24})?')
            or not all(matches(field, r'[0-9a-f]{64}') for field in ('lock_sha256', 'clean_sha256', 'result_sha256'))
            or type(data.get('result_size')) is not int or data['result_size'] <= 0
            or type(data.get('personalized')) is not bool
            or (not data['personalized'] and data['clean_sha256'] != data['result_sha256'])):
        raise ValueError('invalid artifact manifest')
