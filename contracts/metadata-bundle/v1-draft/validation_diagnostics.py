"""Optional offline tooling report; no receiver or database acceptance is implied."""
import hashlib
import json
import validate_bundle as validator

REPORT_VERSION = '1.0.0-draft.1'


def envelope(legacy_report, diagnostics, input_sha256, parsed='passed', structural='passed', semantic='passed'):
    return {
        'format': 'disco-validation-diagnostics', 'report_version': REPORT_VERSION,
        'contract_version': validator.VERSION, 'input_sha256': input_sha256,
        'legacy_report': legacy_report, 'diagnostics': diagnostics,
        'stages': {
            'parsed': {'status': parsed}, 'structural': {'status': structural},
            'semantic': {'status': semantic}, 'mapping': {'status': 'not_run'},
            'raw': {'status': 'unverified', 'verified_assets': 0},
            'database': {'status': 'unsupported', 'checked': False},
        },
    }


def failure(error, *, raw=None, capability=False, parsed='failed'):
    """No location is fabricated for parser, I/O or validator-capability failure."""
    code='validator_capability' if capability else 'input'
    stage='structural' if capability else 'parsed'
    legacy=validator.report(None,[{'code':'input','path':'$','message':str(error)}],[])
    diagnostic={'code':code,'stage':stage,'instance_pointer':None,'schema_pointer':None,
                'source_pointer':None,'message':str(error)}
    if isinstance(error,json.JSONDecodeError):
        diagnostic['parser_location']={'line':error.lineno,'column':error.colno,'character_offset':error.pos}
    return envelope(legacy,[diagnostic],hashlib.sha256(raw).hexdigest() if raw is not None else None,
                    parsed, 'unsupported' if capability else 'not_run','not_run')


def validate_bytes(raw: bytes, schema: dict) -> dict:
    """Validate original bytes using the existing bounded parser and validator.

    schema is the explicit trusted local contract loaded by the caller. Unsupported
    schema vocabulary is a tooling failure, not a general JSON Schema judgment.
    Legacy valid means offline draft validation only. This function performs no I/O.
    """
    try:
        data=validator.loads(raw)
    except (ValueError,TypeError,RecursionError,OverflowError) as error:
        return failure(error,raw=raw)
    locations={}
    try:
        legacy=validator.validate(data,schema,_locations=locations)
    except validator.UnsupportedSchema as error:
        return failure(error,raw=raw,capability=True,parsed='passed')
    except (ValueError,TypeError,KeyError,RecursionError,OverflowError) as error:
        # Invalid schema/configuration must fail closed without a false data verdict.
        return failure(error,raw=raw,capability=True,parsed='passed')
    diagnostics=[]
    for error in legacy['errors']:
        location=locations.get(id(error),{'stage':'semantic','instance_pointer':None,'schema_pointer':None,'source_pointer':None})
        diagnostics.append({'code':error['code'],**location,'message':error['message']})
    structural='failed' if any(d['stage']=='structural' for d in diagnostics) else 'passed'
    semantic='not_run' if structural=='failed' else ('failed' if diagnostics else 'passed')
    return envelope(legacy,diagnostics,hashlib.sha256(raw).hexdigest(),structural=structural,semantic=semantic)
