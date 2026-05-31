-- Narrative Context: Volume Spike Detection
-- Compares current volume to historical baseline to flag anomalies
-- Parameters: {{time_window_hours}} (e.g. 1, 6, 24), {{spike_multiplier}} (e.g. 2.0 = 2x normal)

WITH hourly_volume AS (
    SELECT
        date_trunc('hour', block_time)  AS hour,
        token_bought_address            AS token_address,
        token_bought_symbol             AS symbol,
        SUM(amount_usd)                 AS volume_usd,
        COUNT(*)                        AS trade_count,
        COUNT(DISTINCT taker)           AS unique_traders
    FROM dex.trades
    WHERE blockchain = 'ethereum'
      AND block_time >= NOW() - INTERVAL '7' DAY
      AND token_bought_address IN (
          0xdAC17F958D2ee523a2206206994597C13D831ec7,
          0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48,
          0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599,
          0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2,
          0x514910771AF9Ca656af840dff83E8264EcF986CA,
          0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984,
          0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9,
          0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84,
          0x6B175474E89094C44Da98b954EedeAC495271d0F,
          0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2
      )
    GROUP BY 1, 2, 3
),

baseline AS (
    -- 7-day average excluding the last window (to get true baseline)
    SELECT
        token_address,
        symbol,
        AVG(volume_usd)                 AS avg_hourly_volume,
        STDDEV(volume_usd)              AS stddev_volume,
        AVG(trade_count)                AS avg_hourly_trades
    FROM hourly_volume
    WHERE hour < NOW() - INTERVAL '{{time_window_hours}}' HOUR
    GROUP BY token_address, symbol
),

current_window AS (
    SELECT
        token_address,
        symbol,
        SUM(volume_usd)                 AS current_volume_usd,
        SUM(trade_count)                AS current_trades,
        SUM(unique_traders)             AS current_unique_traders
    FROM hourly_volume
    WHERE hour >= NOW() - INTERVAL '{{time_window_hours}}' HOUR
    GROUP BY token_address, symbol
)

SELECT
    cw.symbol,
    ROUND(cw.current_volume_usd, 2)                         AS current_volume_usd,
    ROUND(b.avg_hourly_volume * {{time_window_hours}}, 2)   AS expected_volume_usd,
    ROUND(cw.current_volume_usd /
          NULLIF(b.avg_hourly_volume * {{time_window_hours}}, 0), 2) AS volume_multiplier,
    cw.current_trades,
    ROUND(b.avg_hourly_trades * {{time_window_hours}}, 0)   AS expected_trades,
    cw.current_unique_traders,
    CASE
        WHEN cw.current_volume_usd / NULLIF(b.avg_hourly_volume * {{time_window_hours}}, 0) >= {{spike_multiplier}} * 2
            THEN '🚨 Extreme Spike (>2x threshold)'
        WHEN cw.current_volume_usd / NULLIF(b.avg_hourly_volume * {{time_window_hours}}, 0) >= {{spike_multiplier}}
            THEN '⚡ Volume Spike Detected'
        WHEN cw.current_volume_usd / NULLIF(b.avg_hourly_volume * {{time_window_hours}}, 0) >= {{spike_multiplier}} * 0.5
            THEN '📊 Elevated Volume'
        ELSE '✅ Normal Volume'
    END AS spike_signal
FROM current_window cw
JOIN baseline b ON cw.token_address = b.token_address
WHERE cw.current_volume_usd / NULLIF(b.avg_hourly_volume * {{time_window_hours}}, 0) >= {{spike_multiplier}} * 0.5
ORDER BY volume_multiplier DESC
