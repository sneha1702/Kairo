-- Bridge Activity: Capital migration between chains.
-- Each row = one (from_chain, to_chain, bridge_name) corridor.
--   gross_inflow_usd  = deposits flowing from_chain → to_chain
--   gross_outflow_usd = withdrawals returning to_chain → from_chain
--   net_flow_usd      = positive means net migration toward to_chain
-- Parameters: {{time_window_hours}}, {{min_usd_value}}, {{end_time}}
-- Note: acceleration_7d_vs_30d_pct is derived by the app from accumulated ES history.

WITH all_flows AS (
    -- Deposits: capital leaving deposit_chain and arriving at withdrawal_chain
    SELECT
        deposit_chain    AS from_chain,
        withdrawal_chain AS to_chain,
        bridge_name,
        deposit_amount_usd AS usd_value,
        'deposit' AS flow_direction
    FROM bridges_evms.deposits
    WHERE block_time >= TIMESTAMP '{{end_time}}' - INTERVAL '{{time_window_hours}}' HOUR
      AND block_time <  TIMESTAMP '{{end_time}}'
      AND deposit_amount_usd >= {{min_usd_value}}

    UNION ALL

    -- Withdrawals: capital returning from withdrawal_chain back to deposit_chain.
    -- Reuse same (deposit_chain, withdrawal_chain) orientation as deposits so both
    -- directions aggregate into the same corridor row.
    SELECT
        deposit_chain    AS from_chain,
        withdrawal_chain AS to_chain,
        bridge_name,
        withdrawal_amount_usd AS usd_value,
        'withdrawal' AS flow_direction
    FROM bridges_evms.withdrawals
    WHERE block_time >= TIMESTAMP '{{end_time}}' - INTERVAL '{{time_window_hours}}' HOUR
      AND block_time <  TIMESTAMP '{{end_time}}'
      AND withdrawal_amount_usd >= {{min_usd_value}}
),

corridor_agg AS (
    SELECT
        from_chain,
        to_chain,
        bridge_name,
        ROUND(SUM(CASE WHEN flow_direction = 'deposit'    THEN usd_value ELSE 0 END), 2) AS gross_inflow_usd,
        ROUND(SUM(CASE WHEN flow_direction = 'withdrawal' THEN usd_value ELSE 0 END), 2) AS gross_outflow_usd,
        COUNT(*) AS tx_count
    FROM all_flows
    GROUP BY from_chain, to_chain, bridge_name
),

totals AS (
    SELECT SUM(gross_inflow_usd + gross_outflow_usd) AS grand_total_usd
    FROM corridor_agg
),

preoutput AS (
    SELECT
        'mixed'                                                                       AS symbol,
        c.from_chain,
        c.to_chain,
        c.bridge_name,
        c.gross_inflow_usd,
        c.gross_outflow_usd,
        ROUND(c.gross_inflow_usd + c.gross_outflow_usd, 2)                            AS bridge_usd,
        ROUND(c.gross_inflow_usd - c.gross_outflow_usd, 2)                            AS net_flow_usd,
        ROUND(c.gross_inflow_usd + c.gross_outflow_usd, 2)                            AS total_usd,
        ROUND(
            (c.gross_inflow_usd + c.gross_outflow_usd) * 100.0
            / NULLIF(t.grand_total_usd, 0), 2
        )                                                                             AS percentage_of_total,
        c.tx_count,
        TIMESTAMP '{{end_time}}'                                                      AS time_bucket,
        'capital_migration'                                                           AS category,
        FILTER(
            ARRAY[
                CASE WHEN c.gross_inflow_usd > c.gross_outflow_usd
                     THEN 'NET_INFLOW_TO_L2' END,
                CASE WHEN c.gross_outflow_usd > c.gross_inflow_usd
                     THEN 'NET_RETURN_TO_L1' END,
                CASE WHEN (c.gross_inflow_usd + c.gross_outflow_usd) > 1000000
                     THEN 'HIGH_BRIDGE_VOLUME' END,
                CASE WHEN ABS(c.gross_inflow_usd - c.gross_outflow_usd)
                          / NULLIF(c.gross_inflow_usd + c.gross_outflow_usd, 0) > 0.8
                     THEN 'STRONG_DIRECTIONAL_FLOW' END
            ],
            x -> x IS NOT NULL
        )                                                                             AS signals
    FROM corridor_agg c
    CROSS JOIN totals t
)

SELECT
    symbol,
    from_chain,
    to_chain,
    bridge_name,
    gross_inflow_usd,
    gross_outflow_usd,
    bridge_usd,
    net_flow_usd,
    total_usd,
    percentage_of_total,
    tx_count,
    time_bucket,
    category,
    signals,
    CARDINALITY(signals) AS signal_count
FROM preoutput
ORDER BY bridge_usd DESC
