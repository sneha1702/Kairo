-- DEX Trading Concentration (Flipside / Snowflake)
-- Table: ethereum.core.ez_dex_swaps
-- Parameters: {{time_window_hours}}, {{min_usd_value}}, {{end_time}}

WITH dex_agg AS (
    SELECT
        token_out_symbol                        AS symbol,
        platform                                AS dex,
        ROUND(SUM(amount_out_usd), 2)           AS volume_usd,
        COUNT(*)                                AS trade_count,
        COUNT(DISTINCT origin_from_address)     AS unique_traders
    FROM ethereum.core.ez_dex_swaps
    WHERE block_timestamp >= TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
      AND block_timestamp <  '{{end_time}}'::TIMESTAMP_NTZ
      AND token_out_symbol IN ('USDT','USDC','WBTC','WETH','LINK','UNI','AAVE','stETH','DAI','MKR')
      AND amount_out_usd >= {{min_usd_value}}
      AND amount_out_usd IS NOT NULL
    GROUP BY token_out_symbol, platform
),

token_totals AS (
    SELECT symbol, SUM(volume_usd) AS token_total_usd
    FROM dex_agg
    GROUP BY symbol
)

SELECT
    d.symbol,
    d.dex,
    d.volume_usd,
    d.trade_count,
    d.unique_traders,
    ROUND(d.volume_usd * 100.0 / NULLIF(tt.token_total_usd, 0), 2)     AS dex_share_pct,
    tt.token_total_usd,
    '{{end_time}}'::TIMESTAMP_NTZ                                       AS time_bucket,
    'dex_liquidity'                                                     AS category,
    ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN d.volume_usd * 100.0 / NULLIF(tt.token_total_usd, 0) > 50   THEN 'DOMINANT_DEX'         ELSE NULL END,
        CASE WHEN d.volume_usd >= 10000000                                      THEN 'HIGH_DEX_VOLUME'      ELSE NULL END,
        CASE WHEN d.unique_traders >= 100                                       THEN 'BROAD_PARTICIPATION'  ELSE NULL END,
        CASE WHEN d.trade_count >= 500                                          THEN 'HIGH_ACTIVITY'        ELSE NULL END
    ))                                                                  AS signals,
    ARRAY_SIZE(ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN d.volume_usd * 100.0 / NULLIF(tt.token_total_usd, 0) > 50   THEN 'DOMINANT_DEX'         ELSE NULL END,
        CASE WHEN d.volume_usd >= 10000000                                      THEN 'HIGH_DEX_VOLUME'      ELSE NULL END,
        CASE WHEN d.unique_traders >= 100                                       THEN 'BROAD_PARTICIPATION'  ELSE NULL END,
        CASE WHEN d.trade_count >= 500                                          THEN 'HIGH_ACTIVITY'        ELSE NULL END
    )))                                                                 AS signal_count
FROM dex_agg d
JOIN token_totals tt ON d.symbol = tt.symbol
ORDER BY d.volume_usd DESC
LIMIT 50
