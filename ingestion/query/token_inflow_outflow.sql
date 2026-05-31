-- Token Flow Context: Exchange Inflows vs Outflows
-- Uses cex.flows Spellbook table (replaces labels.all which is unavailable on free tier)
-- Parameters: {{time_window_hours}} (e.g. 1, 6, 24)

SELECT
    token_symbol                                                                AS token,
    ROUND(SUM(CASE WHEN flow_type = 'inflow'  THEN amount     ELSE 0 END), 2)  AS inflow_tokens,
    ROUND(SUM(CASE WHEN flow_type = 'outflow' THEN amount     ELSE 0 END), 2)  AS outflow_tokens,
    ROUND(SUM(CASE WHEN flow_type = 'inflow'  THEN amount_usd ELSE 0 END), 2)  AS inflow_usd,
    ROUND(SUM(CASE WHEN flow_type = 'outflow' THEN amount_usd ELSE 0 END), 2)  AS outflow_usd,
    ROUND(
        SUM(CASE WHEN flow_type = 'inflow'  THEN amount_usd ELSE 0 END) -
        SUM(CASE WHEN flow_type = 'outflow' THEN amount_usd ELSE 0 END)
    , 2)                                                                        AS net_flow_usd,
    CASE
        WHEN SUM(CASE WHEN flow_type = 'inflow'  THEN amount_usd ELSE 0 END) -
             SUM(CASE WHEN flow_type = 'outflow' THEN amount_usd ELSE 0 END) > 0
            THEN '🔴 Net Inflow (Sell Pressure)'
        ELSE '🟢 Net Outflow (Accumulation)'
    END                                                                         AS signal
FROM cex.flows
WHERE blockchain = 'ethereum'
  AND block_time >= NOW() - INTERVAL '{{time_window_hours}}' HOUR
  AND token_symbol IN ('USDT', 'USDC', 'WBTC', 'WETH', 'LINK', 'UNI', 'AAVE', 'stETH', 'DAI', 'MKR')
  AND amount_usd IS NOT NULL
GROUP BY token_symbol
HAVING SUM(amount_usd) > 0
ORDER BY ABS(
    SUM(CASE WHEN flow_type = 'inflow'  THEN amount_usd ELSE 0 END) -
    SUM(CASE WHEN flow_type = 'outflow' THEN amount_usd ELSE 0 END)
) DESC
