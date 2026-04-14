DOMAIN = "unifi_device_tracker"

CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_VERIFY_SSL = "verify_ssl"
CONF_TRACKED_MACS = "tracked_macs"
CONF_AWAY_DELAY = "away_delay"
CONF_HOME_DELAY = "home_delay"

DEFAULT_AWAY_DELAY = 0  # seconds
DEFAULT_HOME_DELAY = 0  # seconds

UNIFI_LOGIN_PATH = "/api/auth/login"
UNIFI_CLIENTS_PATH = "/proxy/network/api/s/default/stat/sta"
UNIFI_WLANS_PATH = "/proxy/network/api/s/default/rest/wlanconf"
UNIFI_WS_PATH = "/proxy/network/wss/s/default/events"

WS_HEARTBEAT_INTERVAL = 25  # seconds
WS_RECONNECT_MIN_DELAY = 5  # seconds
WS_RECONNECT_MAX_DELAY = 300  # seconds
# Window after a disconnect in which stale sta:sync frames are suppressed
# and brief reconnects (fast WiFi roams) are treated as continuous presence
# so home_delay doesn't re-arm.
WS_DISCONNECT_SUPPRESSION_WINDOW = 15  # seconds
WS_EVENT_STA_SYNC = "sta:sync"
WS_EVENT_EVENTS = "events"
WS_CONNECT_KEYS = {"EVT_WU_Connected", "EVT_WG_Connected"}
WS_DISCONNECT_KEYS = {"EVT_WU_Disconnected", "EVT_WG_Disconnected"}
