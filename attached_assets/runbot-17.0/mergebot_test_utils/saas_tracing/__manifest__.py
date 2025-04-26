{
    "name": "OpenTelemetry instrumentation for Odoo",
    'version': '1.0',
    'license': 'BSD-0-Clause',
    "category": "Hidden",
    'external_dependencies': {
        'python': [
            'opentelemetry',
            'opentelemetry-instrumentation-logging',
            'opentelemetry-instrumentation-psycopg2',
            'opentelemetry-instrumentation-requests',
            'opentelemetry-instrumentation-wsgi',
            'opentelemetry-container-distro',
        ]
    },
}
