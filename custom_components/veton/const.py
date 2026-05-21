"""Constants for the Veton EV Charger integration."""

DOMAIN = "veton"
DEFAULT_PORT = 502
DEFAULT_SLAVE = 1
DEFAULT_CONNECTOR = 1
DEFAULT_SCAN_INTERVAL = 5  # seconds

CONF_CONNECTOR = "connector"

# IEC 61851-1 vehicle status codes
VEHICLE_STATUS = {
    "A1": "Not connected",
    "A2": "Not connected (PWM)",
    "B1": "Connected, not ready",
    "B2": "Connected, ready",
    "C1": "Charging requested",
    "C2": "Charging",
    "E0": "Error",
    "F0": "Not available",
    "IN": "Initializing",
}

# Charging release modes
RELEASE_MODE = {
    0: "Dashboard",
    1: "Local whitelist",
    2: "External control",
    3: "Permanent release",
    4: "OCPP",
    5: "Modbus",
}

# Energy meter types
ENERGY_METER_TYPE = {
    0: "None",
    1: "Phoenix Contact EEM-350-D-MCB",
    2: "Phoenix Contact EEM-EM357",
    3: "Carlo Gavazzi EM24",
    4: "Phoenix Contact EEM-EM357-EE",
    6: "Carlo Gavazzi EM340",
    11: "Iskra WM3M4(C)",
    12: "Inepro Metering PRO380",
    65535: "Unknown",
}
