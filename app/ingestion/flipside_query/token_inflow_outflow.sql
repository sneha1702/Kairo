-- Token Inflow/Outflow — CEX net flow approximation (Flipside / Snowflake)
-- NOTE: Flipside has no direct cex.flows equivalent. This query approximates
-- CEX flows by looking at transfers TO/FROM the top known CEX hot wallets
-- on Ethereum. Cover is partial — add more CEX addresses to cex_wallets as needed.
-- Parameters: {{time_window_hours}}, {{end_time}}

WITH cex_wallets AS (
    SELECT address, exchange FROM (VALUES
        -- Binance
        ('0x28c6c06298d514db089934071355e5743bf21d60', 'Binance'),
        ('0xdfd5293d8e347dfe59e90efd55b2956a1343963d', 'Binance'),
        -- Coinbase
        ('0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43', 'Coinbase'),
        ('0x71660c4005ba85c37ccec55d0c4493e66fe775d3', 'Coinbase'),
        -- Kraken
        ('0x2910543af39aba0cd09dbb2d50200b3e800a63d2', 'Kraken'),
        -- OKX
        ('0x6cc5f688a315f3dc28a7781717a9a798a59fda7b', 'OKX'),
        -- Bybit
        ('0xf89d7b9c864f589bbf53a82105107622b35eaa40', 'Bybit')
    ) AS t(address, exchange)
),

flow_agg AS (
    SELECT
        tr.symbol,
        tr.blockchain                                                           AS blockchain,
        ROUND(SUM(CASE WHEN LOWER(tr.to_address) IN (SELECT address FROM cex_wallets)
                       THEN tr.amount_usd ELSE 0 END), 2)                       AS gross_inflow_usd,
        ROUND(SUM(CASE WHEN LOWER(tr.from_address) IN (SELECT address FROM cex_wallets)
                       THEN tr.amount_usd ELSE 0 END), 2)                       AS gross_outflow_usd,
        ROUND(SUM(CASE WHEN LOWER(tr.to_address) IN (SELECT address FROM cex_wallets)
                       THEN tr.amount ELSE 0 END), 2)                           AS inflow_tokens,
        ROUND(SUM(CASE WHEN LOWER(tr.from_address) IN (SELECT address FROM cex_wallets)
                       THEN tr.amount ELSE 0 END), 2)                           AS outflow_tokens,
        MIN(tr.block_timestamp)                                                 AS earliest_flow_time,
        MAX(tr.block_timestamp)                                                 AS latest_flow_time
    FROM ethereum.core.ez_token_transfers tr
    WHERE tr.block_timestamp >= TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
      AND tr.block_timestamp <  '{{end_time}}'::TIMESTAMP_NTZ
      AND tr.symbol IN ('USDT','USDC','WBTC','WETH','LINK','UNI','AAVE','stETH','DAI','MKR')
      AND tr.amount_usd > 0
      AND tr.amount_usd IS NOT NULL
      AND (
          LOWER(tr.to_address)   IN (SELECT address FROM cex_wallets)
          OR LOWER(tr.from_address) IN (SELECT address FROM cex_wallets)
      )
    GROUP BY tr.symbol, tr.blockchain
    HAVING SUM(tr.amount_usd) > 0
)

SELECT
    symbol,
    CASE WHEN (gross_inflow_usd - gross_outflow_usd) >= 0 THEN blockchain ELSE 'cex' END AS from_chain,
    CASE WHEN (gross_inflow_usd - gross_outflow_usd) >= 0 THEN 'cex' ELSE blockchain END AS to_chain,
    inflow_tokens,
    outflow_tokens,
    gross_inflow_usd,
    gross_outflow_usd,
    ROUND(gross_inflow_usd - gross_outflow_usd, 2)                                        AS net_flow_usd,
    earliest_flow_time,
    latest_flow_time,
    '{{end_time}}'::TIMESTAMP_NTZ                                                         AS time_bucket,
    'capital_migration'                                                                   AS category,
    ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN (gross_inflow_usd - gross_outflow_usd) > 0            THEN 'CEX_INFLOW_PRESSURE'  ELSE NULL END,
        CASE WHEN (gross_inflow_usd - gross_outflow_usd) < 0            THEN 'ACCUMULATION_SIGNAL'  ELSE NULL END,
        CASE WHEN ABS(gross_inflow_usd - gross_outflow_usd) > 1000000   THEN 'HIGH_NET_FLOW'        ELSE NULL END,
        CASE WHEN gross_inflow_usd > 0 AND gross_outflow_usd > 0
              AND ABS(gross_inflow_usd - gross_outflow_usd)
                  / NULLIF(gross_inflow_usd + gross_outflow_usd, 0) < 0.1
                                                                        THEN 'BALANCED_FLOW'        ELSE NULL END
    ))                                                                                    AS signals,
    ARRAY_SIZE(ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN (gross_inflow_usd - gross_outflow_usd) > 0            THEN 'CEX_INFLOW_PRESSURE'  ELSE NULL END,
        CASE WHEN (gross_inflow_usd - gross_outflow_usd) < 0            THEN 'ACCUMULATION_SIGNAL'  ELSE NULL END,
        CASE WHEN ABS(gross_inflow_usd - gross_outflow_usd) > 1000000   THEN 'HIGH_NET_FLOW'        ELSE NULL END,
        CASE WHEN gross_inflow_usd > 0 AND gross_outflow_usd > 0
              AND ABS(gross_inflow_usd - gross_outflow_usd)
                  / NULLIF(gross_inflow_usd + gross_outflow_usd, 0) < 0.1
                                                                        THEN 'BALANCED_FLOW'        ELSE NULL END
    )))                                                                                   AS signal_count
FROM flow_agg
ORDER BY ABS(net_flow_usd) DESC
LIMIT 20
