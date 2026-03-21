"""Shared D-Bus constants for the forgewatch daemon.

These values are used by both the daemon (``dbus_service``) and the
indicator client so that the bus name, object path, and interface name
stay in sync across processes.
"""

BUS_NAME = "org.forgewatch.Daemon"
OBJECT_PATH = "/org/forgewatch/Daemon"
INTERFACE_NAME = "org.forgewatch.Daemon"
