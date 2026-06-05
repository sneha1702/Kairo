-- Token Inflow/Outflow: CEX net flow per token — positive net = sell pressure.
-- Parameters: {{time_window_hours}}, {{end_time}}

WITH flow_agg AS (
    SELECT
        token_symbol                                                                  AS symbol,
        blockchain,
        ROUND(SUM(CASE WHEN flow_type = 'inflow'  THEN amount     ELSE 0 END), 2)    AS inflow_tokens,
        ROUND(SUM(CASE WHEN flow_type = 'outflow' THEN amount     ELSE 0 END), 2)    AS outflow_tokens,
        ROUND(SUM(CASE WHEN flow_type = 'inflow'  THEN amount_usd ELSE 0 END), 2)    AS gross_inflow_usd,
        ROUND(SUM(CASE WHEN flow_type = 'outflow' THEN amount_usd ELSE 0 END), 2)    AS gross_outflow_usd,
        ROUND(
            SUM(CASE WHEN flow_type = 'inflow'  THEN amount_usd ELSE 0 END) -
            SUM(CASE WHEN flow_type = 'outflow' THEN amount_usd ELSE 0 END)
        , 2)                                                                          AS net_flow_usd,
        MIN(block_time)                                                               AS earliest_flow_time,
        MAX(block_time)                                                               AS latest_flow_time
    FROM cex.flows
    WHERE blockchain = 'ethereum'
      AND block_time >= TIMESTAMP '{{end_time}}' - INTERVAL '{{time_window_hours}}' HOUR
      AND block_time <  TIMESTAMP '{{end_time}}'
      AND token_symbol IN ('USDT', 'USDC', 'WBTC', 'WETH', 'LINK', 'UNI', 'AAVE', 'stETH', 'DAI', 'MKR')
      AND amount_usd IS NOT NULL
    GROUP BY token_symbol, blockchain
    HAVING SUM(amount_usd) > 0
),

preoutput AS (
    SELECT
        symbol,
        -- from_chain / to_chain: positive net_flow = tokens moving onto exchange (blockchain → cex)
        CASE WHEN net_flow_usd >= 0 THEN blockchain ELSE 'cex' END    AS from_chain,
        CASE WHEN net_flow_usd >= 0 THEN 'cex' ELSE blockchain END    AS to_chain,
        inflow_tokens,
        outflow_tokens,
        gross_inflow_usd,
        gross_outflow_usd,
        net_flow_usd,
        earliest_flow_time,
        latest_flow_time,
        date_trunc('hour', NOW())                                      AS time_bucket,
        'capital_migration'                                            AS category,
        FILTER(
            ARRAY[
                CASE WHEN net_flow_usd > 0
                     THEN 'CEX_INFLOW_PRESSURE' END,
                CASE WHEN net_flow_usd < 0
                     THEN 'ACCUMULATION_SIGNAL' END,
                CASE WHEN ABS(net_flow_usd) > 1000000
                     THEN 'HIGH_NET_FLOW' END,
                CASE WHEN gross_inflow_usd > 0 AND gross_outflow_usd > 0
                         AND ABS(net_flow_usd) / NULLIF(gross_inflow_usd + gross_outflow_usd, 0) < 0.1
                     THEN 'BALANCED_FLOW' END
            ],
            x -> x IS NOT NULL
        )                                                              AS signals
    FROM flow_agg
)

SELECT
    symbol,
    from_chain,
    to_chain,
    inflow_tokens,
    outflow_tokens,
    gross_inflow_usd,
    gross_outflow_usd,
    net_flow_usd,
    earliest_flow_time,
    latest_flow_time,
    time_bucket,
    category,
    signals,
    CARDINALITY(signals) AS signal_count
FROM preoutput
ORDER BY ABS(net_flow_usd) DESC
