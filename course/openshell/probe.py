"""Run inside the sandbox. A timeout is NOT evidence of policy enforcement."""
import json
from pathlib import Path
from urllib.error import HTTPError
from course.common import request

results = {'allowed_models': bool(request('/v1/models')['data'])}
# /health works on the host but is deliberately absent from the policy.
try:
    request('/health')
except HTTPError as exc:
    results['denied_health_status'] = exc.code
    results['denied_health_body'] = exc.read().decode()[:1000]
    assert exc.code == 403, f'Unexpected response: {exc.code}'
else:
    raise AssertionError('Policy did not deny /health')
# Prove filesystem denial on a world-readable source file owned by sandbox.
try:
    with Path('/opt/course/openshell/canary.txt').open('a') as stream:
        stream.write('should never be written\n')
except PermissionError:
    results['readonly_write_denied'] = True
else:
    raise AssertionError('Read-only course was writable')
Path('/tmp/course-policy-output.txt').write_text('allowed scratch output\n')
results['scratch_write_allowed'] = True
print(json.dumps(results, indent=2))
