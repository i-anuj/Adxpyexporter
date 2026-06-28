import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

import azure.functions as func
from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
from azure.kusto.data import ClientRequestProperties
from datadog_api_client import ApiClient, Configuration
from datadog_api_client.v1.api.events_api import EventsApi
from datadog_api_client.v1.api.metrics_api import MetricsApi
from datadog_api_client.v1.model.event_create_request import EventCreateRequest
from datadog_api_client.v1.model.metrics_payload import MetricsPayload
from datadog_api_client.v1.model.point import Point
from datadog_api_client.v1.model.series import Series

from queries import QUERIES

logger = logging.getLogger("adx_exporter")

ADX_CLUSTER_URL = os.environ["ADX_CLUSTER_URL"]
ADX_DATABASE = "verifi-uat-kusto-devicemessages"
DD_API_KEY = os.environ["DD_API_KEY"]
DD_SITE = "datadoghq.eu"
SERVER_TIMEOUT = timedelta(seconds=60)


def sanitise_row(row):
    return {k: str(v) if v is not None else "unknown" for k, v in row.items()}


def kusto_val(val):
    if val is None:
        return None
    if hasattr(val, "total_seconds"):  # timedelta
        return str(val)
    if hasattr(val, "isoformat"):  # datetime / date
        return val.isoformat()
    try:
        return str(val)
    except Exception:
        return "unknown"


def execute_kql(kusto, kql):
    props = ClientRequestProperties()
    props.set_option("servertimeout", SERVER_TIMEOUT)
    response = kusto.execute(ADX_DATABASE, kql.strip(), properties=props)
    primary = response.primary_results[0]
    columns = [col.column_name for col in primary.columns]
    return [
        {col: kusto_val(val) for col, val in zip(columns, row)} for row in primary.rows
    ]


def safe_str(e):
    try:
        return str(e)
    except Exception:
        return repr(e)


def send_event(client, title, text, alert_type="info", tags=None):
    try:
        body = EventCreateRequest(
            title=title,
            text=text,
            alert_type=alert_type,
            tags=list(tags or []) + ["env:test-verifi-python", "source:adx-exporter"],
        )
        EventsApi(client).create_event(body=body)
    except Exception as e:
        logger.warning("failed to send event [%s]: %s", title, e)


def run_query(kusto, query_def):
    """Runs a single KQL query. Returns (query_def, rows, error)."""
    name = query_def["name"]
    try:
        logger.info("running query: %s", name)
        rows = execute_kql(kusto, query_def["kql"])
        logger.info("%d rows returned for [%s]", len(rows), name)
        return query_def, rows, None
    except Exception as e:
        logger.error("query [%s] failed: %s", name, repr(e))
        return query_def, [], e


app = func.FunctionApp()


@app.timer_trigger(
    schedule="0 */5 * * * *", arg_name="timer", run_on_startup=False, use_monitor=False
)
def adx_exporter(timer: func.TimerRequest) -> None:
    start = time.time()
    logger.info("function started")

    if timer.past_due:
        logger.warning("timer is past due")

    cfg = Configuration()
    cfg.api_key["apiKeyAuth"] = DD_API_KEY
    cfg.server_variables["site"] = DD_SITE

    with ApiClient(cfg) as dd_client:
        kusto = None
        try:
            logger.info("connecting to %s", ADX_CLUSTER_URL)
            kcsb = KustoConnectionStringBuilder.with_aad_managed_service_identity_authentication(
                ADX_CLUSTER_URL
            )
            kusto = KustoClient(kcsb)
            logger.info("kusto client created for %s", ADX_CLUSTER_URL)
        except Exception as e:
            logger.error("failed to connect to ADX: %s", repr(e))
            send_event(
                dd_client,
                "ADX Exporter: ADX connection failed",
                safe_str(e),
                alert_type="error",
            )
            logger.info("total execution time: %.2fs", time.time() - start)
            return  # heartbeat NOT sent — ADX connection failed

        try:
            all_rows = {}
            failed_queries = set()

            with ThreadPoolExecutor(max_workers=max(1, len(QUERIES))) as executor:
                futures = {
                    executor.submit(run_query, kusto, query_def): query_def
                    for query_def in QUERIES
                }
                for future in as_completed(futures, timeout=65):
                    query_def, rows, error = future.result()
                    name = query_def["name"]

                    if error is not None:
                        failed_queries.add(name)
                        send_event(
                            dd_client,
                            f"ADX Exporter: query [{name}] failed",
                            repr(error),
                            alert_type="error",
                            tags=[f"query:{name}"],
                        )

                    all_rows[name] = rows

            now = int(datetime.now(timezone.utc).timestamp())
            all_series = []

            for query_def in QUERIES:
                name = query_def["name"]
                rows = all_rows.get(name, [])

                if not rows:
                    if name not in failed_queries:
                        logger.info("no rows for [%s] — no anomalies to report", name)
                    continue

                logger.info("building series for [%s]...", name)
                built = 0

                for idx, row in enumerate(rows):
                    metric_name = query_def["metric_name"]
                    metric_value = row.get(query_def["metric_value_col"])

                    if metric_value is None:
                        logger.warning(
                            "skipping row %d in [%s]: metric_value is None | row=%s",
                            idx,
                            name,
                            row,
                        )
                        continue

                    try:
                        value = float(metric_value)
                    except (TypeError, ValueError):
                        logger.warning(
                            "skipping row %d in [%s]: metric_value not numeric (%s)",
                            idx,
                            name,
                            metric_value,
                        )
                        continue

                    try:
                        sanitised = sanitise_row(row)
                        tags = query_def["tags_fn"](sanitised)
                    except Exception as e:
                        logger.warning(
                            "skipping row %d in [%s]: tags_fn raised error: %s | row=%s",
                            idx,
                            name,
                            repr(e),
                            row,
                        )
                        continue

                    all_series.append(
                        Series(
                            metric=f"adx.prd.{metric_name}",
                            type="gauge",
                            points=[Point([float(now), value])],
                            tags=tags,
                        )
                    )
                    built += 1

                logger.info("%d series built for [%s]", built, name)

            duration = round(time.time() - start, 2)
            heartbeat_value = 0.0 if failed_queries else 1.0

            all_series.extend(
                [
                    Series(
                        metric="adx.prd.function_heartbeat",
                        type="gauge",
                        points=[Point([float(now), heartbeat_value])],
                        tags=["env:test-verifi-python", "source:adx-exporter"],
                    ),
                    Series(
                        metric="adx.prd.function_duration_seconds",
                        type="gauge",
                        points=[Point([float(now), duration])],
                        tags=["env:test-verifi-python", "source:adx-exporter"],
                    ),
                ]
            )
            logger.info(
                "heartbeat=%.0f | duration=%.2fs | failed_queries=%s",
                heartbeat_value,
                duration,
                failed_queries or "none",
            )

            try:
                logger.info(
                    "sending %d total series to Datadog (%s)...",
                    len(all_series),
                    DD_SITE,
                )
                result = MetricsApi(dd_client).submit_metrics(
                    body=MetricsPayload(series=all_series)
                )
                status = (
                    result.get("status")
                    if isinstance(result, dict)
                    else getattr(result, "status", None)
                )
                if status == "ok":
                    logger.info("all %d metrics sent successfully", len(all_series))
                else:
                    raise Exception(f"unexpected status: {status}")
            except Exception as e:
                logger.error("SEND step failed: %s", repr(e))
                send_event(
                    dd_client,
                    "ADX Exporter: metrics send failed",
                    safe_str(e),
                    alert_type="error",
                )

        except Exception as e:
            logger.error("unexpected error in main flow: %s", repr(e))
            send_event(
                dd_client,
                "ADX Exporter: unexpected error",
                safe_str(e),
                alert_type="error",
            )
            raise
        finally:
            if kusto is not None:
                try:
                    kusto.close()
                except Exception:
                    pass
            logger.info("total execution time: %.2fs", time.time() - start)
