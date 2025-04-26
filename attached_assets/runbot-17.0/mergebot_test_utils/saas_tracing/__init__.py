"""OpenTelemetry instrumentation

- tries to set up the exporting of traces, metrics, and logs based on otel
  semantics
- automatically instruments psycopg2 and requests to trace outbound requests
- instruments db preload, server run to create new traces (or inbound from env)
- instruments WSGI, RPC for inbound traces

.. todo:: instrument crons
.. todo:: instrument subprocess (?)
"""

import functools
import json
import os

from opentelemetry import trace, distro
from opentelemetry.environment_variables import OTEL_LOGS_EXPORTER, OTEL_METRICS_EXPORTER, OTEL_TRACES_EXPORTER
from opentelemetry.instrumentation import psycopg2, requests, wsgi
from opentelemetry.propagate import extract
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION

import odoo.release
import odoo.service

tracer = trace.get_tracer('odoo')


distro.OpenTelemetryDistro().configure()
configurator = distro.OpenTelemetryConfigurator()

conf = {
    "resource_attributes": {
        SERVICE_NAME: odoo.release.product_name,
        SERVICE_VERSION: odoo.release.major_version,
    },
    # OpenTelemetryDistro only set up trace and metrics, and not well (uses setenv)
    "trace_exporter_names": [e] if (e := os.environ.get(OTEL_LOGS_EXPORTER, "otlp")) else [],
    "metric_exporter_names": [e] if (e := os.environ.get(OTEL_METRICS_EXPORTER, "otlp")) else [],
    "log_exporter_names": [e] if (e := os.environ.get(OTEL_TRACES_EXPORTER, "otlp")) else [],
}
# open-telemetry/opentelemetry-pythhon#4340 changed the name (and some semantics)
# of the parameters so need to try new and fall back to old
try:
    configurator.configure(setup_logging_handler=True, **conf)
except TypeError:
    configurator.configure(logging_enabled=True, **conf)

# Breaks server instrumentation when enabled: threads inherit the init context
#   instead of creating a per-request / per-job trace, if we want to propagate
#   tracing through to one-short workers it should be done by hand (using
#   extract/inject)
# ThreadingInstrumentor().instrument()
# adds otel trace/span information to the logrecord which is not what we care about
# LoggingInstrumentor().instrument()

psycopg2.Psycopg2Instrumentor().instrument(
    # instrumenter checks for psycopg2, but dev machines may have
    # psycopg2-binary, if not present odoo literally can't run so no need to
    # check
    skip_dep_check=True,
)
requests.RequestsInstrumentor().instrument()

# FIXME: blacklist /xmlrpc here so it's not duplicated by the instrumentation
#        of execute below, the middleware currently does not support blacklisting
#        (open-telemetry/opentelemetry-python-contrib#2369)
#
# FIXME:
#   - servers which mount `odoo.http.root` (before patched?)
#   - `lazy_property.reset_all(odoo.http.root)`
#   - `patch('odoo.http.root.get_db_router', ...)`
odoo.http.root = wsgi.OpenTelemetryMiddleware(odoo.http.root)
# because there's code which accesses attributes on `odoo.http.root`
wsgi.OpenTelemetryMiddleware.__getattr__ = lambda self, attr: getattr(self.wsgi, attr)

def wraps(obj: object, attr: str):
    """ Wraps the callable ``attr`` of ``obj`` in the decorated callable
    in-place (so patches ``obj``).

    The wrappee is passed as first argument to the wrapper.
    """
    def decorator(fn):
        wrapped = getattr(obj, attr)
        @functools.wraps(wrapped)
        def wrapper(*args, **kw):
            return fn(wrapped, *args, **kw)
        setattr(obj, attr, wrapper)
    return decorator

# instrument / span the method call side of RPC calls so we don't just have an
# opaque "POST /xmlrpc/2"
@wraps(odoo.service.model, 'execute')
def instrumented_execute(wrapped_execute, db, uid, obj, method, *args, **kw):
    with tracer.start_as_current_span( f"{obj}.{method}", attributes={
        "db": db,
        "uid": uid,
        # while attributes can be sequences they can't be map, or nested
        "args": json.dumps(args, default=str),
        "kwargs": json.dumps(kw, default=str),
    }):
        return wrapped_execute(db, uid, obj, method, *args, **kw)

# Instrument the server & preload so we know / can trace what happens during
#   init. Server instrumentation performs context extraction from environment
#   (preload is just nested inside that).

@wraps(odoo.service.server.ThreadedServer, "run")
def instrumented_threaded_start(wrapped_threaded_run, self, preload=None, stop=None):
    with tracer.start_as_current_span("server.threaded.run", context=extract(os.environ)):
        return wrapped_threaded_run(self, preload=preload, stop=stop)

@wraps(odoo.service.server.PreforkServer, "run")
def instrumented_prefork_run(wrapped_prefork_run, self, preload=None, stop=None):
    with tracer.start_as_current_span("server.prefork.run", context=extract(os.environ)):
        return wrapped_prefork_run(self, preload=preload, stop=stop)

@wraps(odoo.service.server, "preload_registries")
def instrumented_preload(wrapped_preload, dbnames):
    with tracer.start_as_current_span("preload", attributes={
        "dbnames": dbnames,
    }):
        return wrapped_preload(dbnames)
