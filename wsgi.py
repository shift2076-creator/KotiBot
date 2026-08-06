from runtime_preflight import validate_requirements


# Validate the environment before server.py initializes any subsystem.
validate_requirements()

from server import app


application = app