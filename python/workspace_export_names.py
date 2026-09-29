"""Names for new exports, frozen in the recipe before artifact publication."""
import datetime as dt
import re
import unicodedata


def export_date(value=None):
    # Browser clients supply their local calendar date. Headless clients use UTC.
    if value is None:
        return dt.datetime.now(dt.timezone.utc).date().isoformat()
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Export date must be YYYY-MM-DD')
    try:
        dt.date.fromisoformat(value)
    except ValueError as error:
        raise ValueError('Export date must be a valid calendar date') from error
    return value


def _stem(value):
    value = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode()
    # Remove an existing generated date so the suffix appears exactly once.
    value = re.sub(r'[_\s\u00b7\u2014-]+\d{4}-\d{2}-\d{2}$', '', value.strip())
    return re.sub(r'[^A-Za-z0-9]+', '_', value).strip('_')[:109].rstrip('_') or 'Selection'


def default_export_name(label, date):
    label = re.sub(r'([a-z])([A-Z])', r'\1 \2', str(label or 'Search')).replace('Cur Inject', 'current injection')
    return f'{_stem(label)}_{export_date(date)}'


def naming_options(name, fallback, date=None):
    date = export_date(date)
    if name is not None and (not isinstance(name, str) or len(name) > 120):
        raise ValueError('Export name must be text of at most 120 characters')
    return {'name': (name or '').strip() or default_export_name(fallback, date),
            'download_naming': {'version': 1, 'date': date}}


def export_download_name(record, suffix):
    options = record.get('recipe', {}).get('options', {})
    naming = options.get('download_naming')
    if not isinstance(naming, dict) or naming.get('version') != 1:
        # Existing exports retain their historical download filename and bytes.
        return f"recordings-{record['dataset_uuid'][:8]}{suffix}"
    return f"{_stem(options.get('name'))}_{export_date(naming['date'])}{suffix}"
