-- Bridge Activity: Capital migration between chains
-- Returns directional bridge corridors (e.g. ETH↔ARB) per token per bridge.
-- Parameters: {{time_window_hours}}, {{min_usd_value}}
-- Note: acceleration_7d_vs_30d_pct is derived by the app from accumulated ES history.

WITH deposit_agg AS (
    SELECT
        COALESCE(token_symbol, 'UNKNOWN')   AS symbol,
        deposit_chain                        AS from_chain,
        withdrawal_chain                     AS to_chain,
        bridge_name,
        SUM(deposit_amount_usd)              AS gross_inflow_usd,
        COUNT(*)                             AS tx_count
    FROM bridges_evms.deposits
    WHERE block_time >= NOW() - INTERVAL '{{time_window_hours}}' HOUR
      AND deposit_amount_usd >= {{min_usd_value}}
    GROUP BY COALESCE(token_symbol, 'UNKNOWN'), deposit_chain, withdrawal_chain, bridge_name
),

withdrawal_agg AS (
    SELECT
        COALESCE(token_symbol, 'UNKNOWN')   AS symbol,
        withdrawal_chain                     AS from_chain,
        deposit_chain                        AS to_chain,
        bridge_name,
        SUM(withdrawal_amount_usd)           AS gross_outflow_usd,
        COUNT(*)                             AS tx_count
    FROM bridges_evms.withdrawals
    WHERE block_time >= NOW() - INTERVAL '{{time_window_hours}}' HOUR
      AND withdrawal_amount_usd >= {{min_usd_value}}
    GROUP BY COALESCE(token_symbol, 'UNKNOWN'), withdrawal_chain, deposit_chain, bridge_name
),

-- Each row = one bidirectional corridor (from_chain↔to_chain) per symbol per bridge.
-- deposit_agg.from_chain matches withdrawal_agg.to_chain (e.g. ETH→ARB pairs with ARB→ETH).
combined AS (
    SELECT
        COALESCE(d.symbol,      w.symbol)      AS symbol,
        COALESCE(d.from_chain,  w.to_chain)    AS from_chain,
        COALESCE(d.to_chain,    w.from_chain)  AS to_chain,
        COALESCE(d.bridge_name, w.bridge_name) AS bridge_name,
        COALESCE(d.gross_inflow_usd,  0)       AS gross_inflow_usd,
        COALESCE(w.gross_outflow_usd, 0)       AS gross_outflow_usd,
        COALESCE(d.tx_count, 0) + COALESCE(w.tx_count, 0) AS tx_count
    FROM deposit_agg d
    FULL OUTER JOIN withdrawal_agg w
        ON  d.symbol      = w.symbol
        AND d.from_chain  = w.to_chain
        AND d.to_chain    = w.from_chain
        AND d.bridge_name = w.bridge_name
),

totals AS (
    SELECT SUM(gross_inflow_usd + gross_outflow_usd) AS grand_total_usd FROM combined
),

final AS (
    SELECT
        c.symbol,
        c.from_chain,
        c.to_chain,
        c.bridge_name,
        ROUND(c.gross_inflow_usd, 2)                                             AS gross_inflow_usd,
        ROUND(c.gross_outflow_usd, 2)                                            AS gross_outflow_usd,
        ROUND(c.gross_inflow_usd + c.gross_outflow_usd, 2)                       AS bridge_usd,
        ROUND(c.gross_inflow_usd - c.gross_outflow_usd, 2)                       AS net_flow_usd,
        ROUND(c.gross_inflow_usd + c.gross_outflow_usd, 2)                       AS total_usd,
        ROUND(
            (c.gross_inflow_usd + c.gross_outflow_usd) * 100.0
            / NULLIF(t.grand_total_usd, 0), 2
        )                                                                        AS percentage_of_total,
        c.tx_count,
        date_trunc('hour', NOW())                                                AS time_bucket,
        'capital_migration'                                                      AS category,
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
        )                                                                        AS signals
    FROM combined c
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
FROM final
ORDER BY bridge_usd DESC
