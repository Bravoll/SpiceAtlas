"""Non-secret identity shared by the desktop launcher and local ASGI server."""
import hashlib
import os
from pathlib import Path

APP_ID = 'spice-atlas-local'


def project_key(root):
    return hashlib.sha256(os.path.normcase(str(Path(root).resolve())).encode('utf-8')).hexdigest()[:24]


def runtime_identity(root):
    return {'app_id': APP_ID, 'project_key': project_key(root),
            'instance_id': os.environ.get('SPICE_LAUNCHER_INSTANCE', 'console'),
            'managed': bool(os.environ.get('SPICE_LAUNCHER_CONTROL_TOKEN'))}
