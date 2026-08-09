from server_core.preflight import validate_requirements


# Validate the environment before kotibot_server.py initializes any subsystem.
validate_requirements()

from kotibot_server import app


application = app