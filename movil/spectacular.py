"""Hooks de drf-spectacular para la API movil v2.

El schema v2 documenta exclusivamente los endpoints bajo /api/v2/; el resto de
la superficie de escandio (web, legacy movil, API externa) queda fuera.
"""


def solo_endpoints_v2(endpoints):
    """PREPROCESSING_HOOK: filtra el schema a las rutas /api/v2/."""
    return [
        (path, path_regex, method, callback)
        for (path, path_regex, method, callback) in endpoints
        if path.startswith('/api/v2/') and not path.startswith('/api/v2/schema')
    ]
