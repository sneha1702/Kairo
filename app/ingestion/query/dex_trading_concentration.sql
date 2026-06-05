-- DEX Trading Concentration: Which DEXes and wallets dominate trading for top tokens.
-- volume_multiplier compares current window to prior window of equal length.
-- Parameters: {{time_window_hours}}, {{end_time}}

WITH token_dex_volume AS (
    SELECT
        project                          AS dex,
        token_bought_address             AS token_address,
        token_bought_symbol              AS symbol,
        project_contract_address         AS pool,
        SUM(amount_usd)                  AS volume_usd,
        COUNT(*)                         AS trade_count,
        COUNT(DISTINCT taker)            AS unique_traders,
        AVG(amount_usd)                  AS avg_trade_size_usd,
        MIN(block_time)                  AS earliest_trade_time,
        MAX(block_time)                  AS latest_trade_time
    FROM dex.trades
    WHERE blockchain = 'ethereum'
      AND block_time >= TIMESTAMP '{{end_time}}' - INTERVAL '{{time_window_hours}}' HOUR
      AND block_time <  TIMESTAMP '{{end_time}}'
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
    GROUP BY 1, 2, 3, 4
),

total_by_token AS (
    SELECT token_address, SUM(volume_usd) AS total_volume_usd
    FROM token_dex_volume
    GROUP BY token_address
),

-- Prior window: same duration, immediately before the current window
prior_volume_by_token AS (
    SELECT
        token_bought_address AS token_address,
        SUM(amount_usd)      AS prior_volume_usd
    FROM dex.trades
    WHERE blockchain = 'ethereum'
      AND block_time >= TIMESTAMP '{{end_time}}' - 2 * INTERVAL '{{time_window_hours}}' HOUR
      AND block_time <  TIMESTAMP '{{end_time}}' - INTERVAL '{{time_window_hours}}' HOUR
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
    GROUP BY token_bought_address
),

top_traders AS (
    SELECT
        token_bought_address   AS token_address,
        taker                  AS wallet,
        SUM(amount_usd)        AS volume_usd,
        COUNT(*)               AS trade_count,
        ROW_NUMBER() OVER (
            PARTITION BY token_bought_address
            ORDER BY SUM(amount_usd) DESC
        )                      AS rank
    FROM dex.trades
    WHERE blockchain = 'ethereum'
      AND block_time >= TIMESTAMP '{{end_time}}' - INTERVAL '{{time_window_hours}}' HOUR
      AND block_time <  TIMESTAMP '{{end_time}}'
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
    GROUP BY token_bought_address, taker
),

top10_concentration AS (
    SELECT
        tt.token_address,
        ROUND(SUM(tt.volume_usd) * 100.0 / NULLIF(tb.total_volume_usd, 0), 2) AS whale_concentration_pct
    FROM top_traders tt
    JOIN total_by_token tb ON tt.token_address = tb.token_address
    WHERE tt.rank <= 10
    GROUP BY tt.token_address, tb.total_volume_usd
),

preoutput AS (
    SELECT
        tdv.symbol,
        tdv.dex,
        ROUND(tdv.volume_usd, 2)                                                   AS pool_volume_usd,
        tdv.trade_count,
        tdv.unique_traders,
        ROUND(tdv.avg_trade_size_usd, 2)                                           AS avg_trade_usd,
        ROUND(tdv.volume_usd * 100.0 / NULLIF(tb.total_volume_usd, 0), 2)         AS dex_share_pct,
        c.whale_concentration_pct,
        ROUND(tb.total_volume_usd / NULLIF(pv.prior_volume_usd, 0), 2)            AS volume_multiplier,
        tdv.earliest_trade_time,
        tdv.latest_trade_time,
        date_trunc('hour', NOW())                                                  AS time_bucket,
        'ecosystem_rotation'                                                       AS category,
        FILTER(
            ARRAY[
                CASE WHEN tdv.volume_usd * 100.0 / NULLIF(tb.total_volume_usd, 0) > 50
                     THEN 'HIGH_DEX_SHARE' END,
                CASE WHEN c.whale_concentration_pct > 70
                     THEN 'WHALE_DOMINATED' END,
                CASE WHEN tb.total_volume_usd / NULLIF(pv.prior_volume_usd, 0) > 2
                     THEN 'VOLUME_SPIKE' END,
                CASE WHEN c.whale_concentration_pct > 40
                         AND c.whale_concentration_pct <= 70
                     THEN 'CONCENTRATED_TRADING' END
            ],
            x -> x IS NOT NULL
        )                                                                          AS signals
    FROM token_dex_volume tdv
    JOIN total_by_token tb         ON tdv.token_address = tb.token_address
    JOIN top10_concentration c     ON tdv.token_address = c.token_address
    LEFT JOIN prior_volume_by_token pv ON tdv.token_address = pv.token_address
)

SELECT
    symbol,
    dex,
    pool_volume_usd,
    trade_count,
    unique_traders,
    avg_trade_usd,
    dex_share_pct,
    whale_concentration_pct,
    volume_multiplier,
    earliest_trade_time,
    latest_trade_time,
    time_bucket,
    category,
    signals,
    CARDINALITY(signals) AS signal_count
FROM preoutput
ORDER BY pool_volume_usd DESC
LIMIT 50
