-- Volume Spike Detection (Flipside / Snowflake)
-- Table: ethereum.core.ez_dex_swaps
-- Parameters: {{time_window_hours}}, {{spike_multiplier}}, {{end_time}}

WITH hourly_volume AS (
    SELECT
        DATE_TRUNC('hour', block_timestamp)     AS hour,
        token_out_address                       AS token_address,
        token_out_symbol                        AS symbol,
        SUM(amount_out_usd)                     AS volume_usd,
        COUNT(*)                                AS trade_count,
        COUNT(DISTINCT origin_from_address)     AS unique_traders
    FROM ethereum.core.ez_dex_swaps
    WHERE block_timestamp >= TIMESTAMPADD(HOUR, -2 * {{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
      AND block_timestamp <  '{{end_time}}'::TIMESTAMP_NTZ
      AND token_out_symbol IN ('USDT','USDC','WBTC','WETH','LINK','UNI','AAVE','stETH','DAI','MKR')
      AND amount_out_usd IS NOT NULL
    GROUP BY 1, 2, 3
),

baseline AS (
    SELECT
        token_address,
        symbol,
        AVG(volume_usd)     AS avg_hourly_volume,
        STDDEV(volume_usd)  AS stddev_volume,
        AVG(trade_count)    AS avg_hourly_trades
    FROM hourly_volume
    WHERE hour < TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
    GROUP BY token_address, symbol
),

current_window AS (
    SELECT
        token_address,
        symbol,
        SUM(volume_usd)          AS current_volume_usd,
        SUM(trade_count)         AS current_trades,
        SUM(unique_traders)      AS current_unique_traders,
        MIN(hour)                AS window_start_time,
        MAX(hour)                AS window_end_time
    FROM hourly_volume
    WHERE hour >= TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
      AND hour <  '{{end_time}}'::TIMESTAMP_NTZ
    GROUP BY token_address, symbol
)

SELECT
    cw.symbol,
    ROUND(cw.current_volume_usd, 2)                                                 AS current_volume_usd,
    ROUND(b.avg_hourly_volume * {{time_window_hours}}, 2)                           AS expected_volume_usd,
    ROUND(cw.current_volume_usd
          / NULLIF(b.avg_hourly_volume * {{time_window_hours}}, 0), 2)              AS volume_multiplier,
    cw.current_trades,
    ROUND(b.avg_hourly_trades * {{time_window_hours}}, 0)                           AS expected_trades,
    cw.current_unique_traders,
    cw.window_start_time,
    cw.window_end_time,
    '{{end_time}}'::TIMESTAMP_NTZ                                                   AS time_bucket,
    'ecosystem_rotation'                                                            AS category,
    ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN cw.current_volume_usd / NULLIF(b.avg_hourly_volume * {{time_window_hours}}, 0) >= {{spike_multiplier}} * 2
                                                        THEN 'EXTREME_SPIKE'        ELSE NULL END,
        CASE WHEN cw.current_volume_usd / NULLIF(b.avg_hourly_volume * {{time_window_hours}}, 0) >= {{spike_multiplier}}
              AND cw.current_volume_usd / NULLIF(b.avg_hourly_volume * {{time_window_hours}}, 0) <  {{spike_multiplier}} * 2
                                                        THEN 'VOLUME_SPIKE'         ELSE NULL END,
        CASE WHEN cw.current_volume_usd / NULLIF(b.avg_hourly_volume * {{time_window_hours}}, 0) >= {{spike_multiplier}} * 0.5
              AND cw.current_volume_usd / NULLIF(b.avg_hourly_volume * {{time_window_hours}}, 0) <  {{spike_multiplier}}
                                                        THEN 'ELEVATED_VOLUME'      ELSE NULL END,
        CASE WHEN cw.current_volume_usd > b.avg_hourly_volume * {{time_window_hours}}
                                                        THEN 'ACCELERATING'         ELSE NULL END
    ))                                                                              AS signals,
    ARRAY_SIZE(ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN cw.current_volume_usd / NULLIF(b.avg_hourly_volume * {{time_window_hours}}, 0) >= {{spike_multiplier}} * 2
                                                        THEN 'EXTREME_SPIKE'        ELSE NULL END,
        CASE WHEN cw.current_volume_usd / NULLIF(b.avg_hourly_volume * {{time_window_hours}}, 0) >= {{spike_multiplier}}
              AND cw.current_volume_usd / NULLIF(b.avg_hourly_volume * {{time_window_hours}}, 0) <  {{spike_multiplier}} * 2
                                                        THEN 'VOLUME_SPIKE'         ELSE NULL END,
        CASE WHEN cw.current_volume_usd / NULLIF(b.avg_hourly_volume * {{time_window_hours}}, 0) >= {{spike_multiplier}} * 0.5
              AND cw.current_volume_usd / NULLIF(b.avg_hourly_volume * {{time_window_hours}}, 0) <  {{spike_multiplier}}
                                                        THEN 'ELEVATED_VOLUME'      ELSE NULL END,
        CASE WHEN cw.current_volume_usd > b.avg_hourly_volume * {{time_window_hours}}
                                                        THEN 'ACCELERATING'         ELSE NULL END
    )))                                                                             AS signal_count
FROM current_window cw
JOIN baseline b ON cw.token_address = b.token_address
WHERE cw.current_volume_usd
      / NULLIF(b.avg_hourly_volume * {{time_window_hours}}, 0) >= {{spike_multiplier}} * 0.5
ORDER BY volume_multiplier DESC
LIMIT 10
