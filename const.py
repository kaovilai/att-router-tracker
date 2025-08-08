"""Constants for AT&T Router Tracker."""

DOMAIN = "att_router_tracker"

DEFAULT_HOST = "192.168.1.254"
DEFAULT_SCAN_INTERVAL = 30  # seconds

CONF_SESSION_ID = "session_id"
CONF_ACCESS_CODE = "access_code"
CONF_AUTH_METHOD = "auth_method"
CONF_ALWAYS_HOME_DEVICES = "always_home_devices"
CONF_PRESENCE_DETECTION = "presence_detection"

AUTH_METHOD_ACCESS_CODE = "access_code"
AUTH_METHOD_SESSION_ID = "session_id"

ATTR_MAC = "mac_address"
ATTR_IP = "ip_address"
ATTR_NAME = "name"
ATTR_STATUS = "status"
ATTR_CONNECTION_TYPE = "connection_type"
ATTR_LAST_ACTIVITY = "last_activity"
ATTR_ALLOCATION = "allocation"
ATTR_CONNECTION_SPEED = "connection_speed"
ATTR_SIGNAL_STRENGTH = "signal_strength"
ATTR_DEVICE_TYPE = "device_type"

DEVICE_TYPE_ALWAYS_HOME = "always_home"
DEVICE_TYPE_TRACKED = "tracked"