"""Real traffic — GA4 export in BigQuery, by the site's ga4_property_id.

Dataset convention: analytics_<propertyId>. Degrades gracefully (clear note) if the
BQ project / service-account creds aren't configured or the dataset isn't accessible.
"""
from __future__ import annotations

import os

from sqlmodel import Session, select

from ..config import GA4_BQ_PROJECT, GOOGLE_APPLICATION_CREDENTIALS
from ..db import engine
from ..models import Site


def _ga4_property(domain: str) -> str | None:
    with Session(engine) as s:
        site = s.exec(select(Site).where(Site.domain == domain)).first()
        return site.ga4_property_id if site else None


def get_traffic(domain: str) -> dict:
    prop = _ga4_property(domain)
    if not prop:
        return {"domain": domain, "sessions_30d": None, "note": "no GA4 property on this site"}
    if not (GA4_BQ_PROJECT and GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(GOOGLE_APPLICATION_CREDENTIALS)):
        return {"domain": domain, "sessions_30d": None,
                "note": "BigQuery not configured (set GA4_BQ_PROJECT + GOOGLE_APPLICATION_CREDENTIALS)"}
    dataset = f"analytics_{prop}"
    try:
        from google.cloud import bigquery  # lazy import

        client = bigquery.Client(project=GA4_BQ_PROJECT)
        q = f"""
        SELECT COUNT(DISTINCT CONCAT(user_pseudo_id, CAST((
                 SELECT value.int_value FROM UNNEST(event_params) WHERE key='ga_session_id'
               ) AS STRING))) AS sessions
        FROM `{GA4_BQ_PROJECT}.{dataset}.events_*`
        WHERE _TABLE_SUFFIX BETWEEN
              FORMAT_DATE('%Y%m%d', DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
          AND FORMAT_DATE('%Y%m%d', CURRENT_DATE())
        """
        rows = list(client.query(q).result())
        sessions = int(rows[0].sessions) if rows and rows[0].sessions is not None else 0
        return {"domain": domain, "ga4_property_id": prop, "dataset": dataset,
                "sessions_30d": sessions, "source": "GA4 BigQuery export"}
    except Exception as exc:  # noqa: BLE001 - degrade gracefully
        return {"domain": domain, "sessions_30d": None, "dataset": dataset,
                "error": f"{type(exc).__name__}: {exc}"}
