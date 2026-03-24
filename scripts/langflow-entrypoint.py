#!/usr/bin/env python3
"""Entrypoint for the OpenRAG Langflow container.

Runs as root to correct /app/langflow-data bind-mount permissions, then drops
to uid/gid 1000 (langflow user) before exec-ing the main process.

On macOS with Podman the virtiofs layer does not faithfully propagate
host-side chmod into the container, so permissions must be fixed from
inside the container after the mount is established.
"""
import os
import pathlib
import sys

data_dir = pathlib.Path("/app/langflow-data")

try:
    data_dir.chmod(0o777)
except OSError:
    pass

# Drop from root to langflow (uid=1000, gid=1000).
os.setgid(1000)
os.setuid(1000)

os.execvp(sys.argv[1], sys.argv[1:])
