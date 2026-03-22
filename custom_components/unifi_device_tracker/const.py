DOMAIN = "unifi_device_tracker"

CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_VERIFY_SSL = "verify_ssl"
CONF_TRACKED_MACS = "tracked_macs"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_AWAY_DELAY = "away_delay"
CONF_HOME_DELAY = "home_delay"

DEFAULT_SCAN_INTERVAL = 30  # seconds
DEFAULT_AWAY_DELAY = 0  # seconds
DEFAULT_HOME_DELAY = 0  # seconds

UNIFI_LOGIN_PATH = "/api/auth/login"
UNIFI_CLIENTS_PATH = "/proxy/network/api/s/default/stat/sta"
