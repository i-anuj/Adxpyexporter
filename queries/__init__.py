import os

_DIR = os.path.dirname(__file__)


def _load(filename):
    with open(os.path.join(_DIR, filename)) as f:
        return f.read()


def safe_tag(key, value):
    if value is None:
        str_value = "unknown"
    else:
        str_value = str(value)
    str_value = str_value.replace(":", "_")
    return f"{key}:{str_value}"


# -----------------------------------------------------------------------
# Each entry needs:
#   name             — unique identifier for logging
#   metric_name      — Datadog metric name (adx.prd.<metric_name>)
#   metric_value_col — which KQL result column holds the numeric value
#   tags_fn          — function that returns list of Datadog tags from a row
#   kql              — loaded from the matching .kql file
# -----------------------------------------------------------------------

QUERIES = [
    {
        "name": "begin_pour_no_ticket",
        "metric_name": "begin_pour_no_ticket",
        "metric_value_col": "NTs",
        "tags_fn": lambda row: [
            safe_tag("account", row.get("Account", "unknown")),
            "env:test-verifi-python",
        ],
        "kql": _load("begin_pour_no_ticket.kql"),
    },
    {
        "name": "truckless_concrete_status",
        "metric_name": "truckless_concrete_status",
        "metric_value_col": "Messages",
        "tags_fn": lambda row: [
            safe_tag("account", row.get("Account", "unknown")),
            safe_tag("truck_name", row.get("TruckName", "unknown")),
            safe_tag("sender_mac_id", row.get("SenderMacId", "unknown")),
            "env:test-verifi-python",
        ],
        "kql": _load("truckless_concrete_status.kql"),
    },
    {
    "name": "ticket_received_count",
    "metric_name": "ticket_received_count",
    "metric_value_col": "Messages",
    "tags_fn": lambda row: [
        safe_tag("location_id", row.get("LocationId", "unknown")),
        "env:test-verifi-python",
    ],
    "kql": _load("ticket_received_count.kql"),
},
    {
    "name": "unknown_location_status_total",
    "metric_name": "unknown_location_status.total_requests",
    "metric_value_col": "total_requests",
    "tags_fn": lambda row: ["env:test-verifi-python"],
    "kql": _load("unknown_location_status.kql"),
},
{
    "name": "unknown_location_status_unknown",
    "metric_name": "unknown_location_status.unknown_count",
    "metric_value_col": "unknown_count",
    "tags_fn": lambda row: ["env:test-verifi-python"],
    "kql": _load("unknown_location_status.kql"),
},
{
    "name": "unknown_location_status_pct",
    "metric_name": "unknown_location_status.unknown_pct",
    "metric_value_col": "unknown_pct",
    "tags_fn": lambda row: ["env:test-verifi-python"],
    "kql": _load("unknown_location_status.kql"),
},
{
    "name": "unknown_location_status_unknown_trucks",
    "metric_name": "unknown_location_status.truck_status",
    "metric_value_col": "value",
    "tags_fn": lambda row: [
        "env:test-verifi-python",
        f"truck_name:{row.get('truckName', 'unknown')}",
        f"account:{row.get('accountName', 'unknown')}",
        f"account_id:{row.get('accountId', 'unknown')}",
        f"status:{row.get('status', 'unknown')}",
    ],
    "kql": _load("unknown_location_status_unknown_trucks.kql"),
},
{
    "name": "geofence_request_count",
    "metric_name": "geofence_request_count",
    "metric_value_col": "request_count",
    "tags_fn": lambda row: [
        safe_tag("truck_name", row.get("truckName", "unknown")),
        safe_tag("account_id", row.get("accountId", "unknown")),
        safe_tag("account", row.get("accountName", "unknown")),
        "env:test-verifi-python",
    ],
    "kql": _load("geofence_request_count.kql"),
},
    # To add a new query:
    # 1. Create queries/your_query_name.kql
    # 2. Add an entry here following the same structure
]
