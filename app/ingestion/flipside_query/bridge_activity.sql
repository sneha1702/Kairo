-- Bridge Activity (Flipside / Snowflake)
-- Table: crosschain.core.ez_bridge_activity
--   source_chain / destination_chain identify the corridor
--   direction: 'INBOUND' = arriving on this chain, 'OUTBOUND' = leaving
-- Parameters: {{time_window_hours}}, {{min_usd_value}}, {{end_time}}

WITH all_flows AS (
    SELECT
        source_chain                            AS from_chain,
        destination_chain                       AS to_chain,
        platform                                AS bridge_name,
        amount_usd                              AS usd_value,
        direction
    FROM crosschain.core.ez_bridge_activity
    WHERE block_timestamp >= TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
      AND block_timestamp <  '{{end_time}}'::TIMESTAMP_NTZ
      AND amount_usd >= {{min_usd_value}}
      AND amount_usd IS NOT NULL
),

corridor_agg AS (
    SELECT
        from_chain,
        to_chain,
        bridge_name,
        ROUND(SUM(CASE WHEN direction = 'OUTBOUND' THEN usd_value ELSE 0 END), 2) AS gross_inflow_usd,
        ROUND(SUM(CASE WHEN direction = 'INBOUND'  THEN usd_value ELSE 0 END), 2) AS gross_outflow_usd,
        COUNT(*) AS tx_count
    FROM all_flows
    GROUP BY from_chain, to_chain, bridge_name
),

totals AS (
    SELECT SUM(gross_inflow_usd + gross_outflow_usd) AS grand_total_usd
    FROM corridor_agg
)

SELECT
    'mixed'                                                                         AS symbol,
    c.from_chain,
    c.to_chain,
    c.bridge_name,
    c.gross_inflow_usd,
    c.gross_outflow_usd,
    ROUND(c.gross_inflow_usd + c.gross_outflow_usd, 2)                              AS bridge_usd,
    ROUND(c.gross_inflow_usd - c.gross_outflow_usd, 2)                              AS net_flow_usd,
    ROUND(c.gross_inflow_usd + c.gross_outflow_usd, 2)                              AS total_usd,
    ROUND((c.gross_inflow_usd + c.gross_outflow_usd) * 100.0
          / NULLIF(t.grand_total_usd, 0), 2)                                        AS percentage_of_total,
    c.tx_count,
    '{{end_time}}'::TIMESTAMP_NTZ                                                   AS time_bucket,
    'capital_migration'                                                             AS category,
    ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN c.gross_inflow_usd > c.gross_outflow_usd                  THEN 'NET_INFLOW_TO_L2'          ELSE NULL END,
        CASE WHEN c.gross_outflow_usd > c.gross_inflow_usd                  THEN 'NET_RETURN_TO_L1'          ELSE NULL END,
        CASE WHEN (c.gross_inflow_usd + c.gross_outflow_usd) > 1000000      THEN 'HIGH_BRIDGE_VOLUME'        ELSE NULL END,
        CASE WHEN ABS(c.gross_inflow_usd - c.gross_outflow_usd)
                  / NULLIF(c.gross_inflow_usd + c.gross_outflow_usd, 0) > 0.8
                                                                            THEN 'STRONG_DIRECTIONAL_FLOW'   ELSE NULL END
    ))                                                                              AS signals,
    ARRAY_SIZE(ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN c.gross_inflow_usd > c.gross_outflow_usd                  THEN 'NET_INFLOW_TO_L2'          ELSE NULL END,
        CASE WHEN c.gross_outflow_usd > c.gross_inflow_usd                  THEN 'NET_RETURN_TO_L1'          ELSE NULL END,
        CASE WHEN (c.gross_inflow_usd + c.gross_outflow_usd) > 1000000      THEN 'HIGH_BRIDGE_VOLUME'        ELSE NULL END,
        CASE WHEN ABS(c.gross_inflow_usd - c.gross_outflow_usd)
                  / NULLIF(c.gross_inflow_usd + c.gross_outflow_usd, 0) > 0.8
                                                                            THEN 'STRONG_DIRECTIONAL_FLOW'   ELSE NULL END
    )))                                                                             AS signal_count
FROM corridor_agg c
CROSS JOIN totals t
ORDER BY bridge_usd DESC
LIMIT 50
