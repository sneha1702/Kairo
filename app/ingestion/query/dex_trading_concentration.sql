-- Narrative Context: DEX Trading Concentration
-- Shows which DEXes, pools, and wallets dominate trading for top tokens
-- Parameters: {{time_window_hours}} (e.g. 1, 6, 24), {{token_address}} (optional, leave blank for top 10)

WITH token_dex_volume AS (
    SELECT
        project                                             AS dex,
        token_bought_address                                AS token_address,
        token_bought_symbol                                 AS symbol,
        project_contract_address                            AS pool,
        SUM(amount_usd)                                     AS volume_usd,
        COUNT(*)                                            AS trade_count,
        COUNT(DISTINCT taker)                               AS unique_traders,
        AVG(amount_usd)                                     AS avg_trade_size_usd,
        MIN(block_time)                                     AS earliest_trade_time,
        MAX(block_time)                                     AS latest_trade_time
    FROM dex.trades
    WHERE blockchain = 'ethereum'
      AND block_time >= NOW() - INTERVAL '{{time_window_hours}}' HOUR
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
    SELECT
        token_address,
        SUM(volume_usd) AS total_volume_usd
    FROM token_dex_volume
    GROUP BY token_address
),

top_traders AS (
    SELECT
        token_bought_address                                AS token_address,
        taker                                               AS wallet,
        SUM(amount_usd)                                     AS volume_usd,
        COUNT(*)                                            AS trade_count,
        ROW_NUMBER() OVER (
            PARTITION BY token_bought_address
            ORDER BY SUM(amount_usd) DESC
        )                                                   AS rank
    FROM dex.trades
    WHERE blockchain = 'ethereum'
      AND block_time >= NOW() - INTERVAL '{{time_window_hours}}' HOUR
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
        SUM(tt.volume_usd)              AS top10_volume,
        tb.total_volume_usd,
        ROUND(SUM(tt.volume_usd) * 100.0 / NULLIF(tb.total_volume_usd, 0), 2) AS top10_pct
    FROM top_traders tt
    JOIN total_by_token tb ON tt.token_address = tb.token_address
    WHERE tt.rank <= 10
    GROUP BY tt.token_address, tb.total_volume_usd
)

SELECT
    tdv.symbol,
    tdv.dex,
    ROUND(tdv.volume_usd, 2)            AS pool_volume_usd,
    tdv.trade_count,
    tdv.unique_traders,
    ROUND(tdv.avg_trade_size_usd, 2)    AS avg_trade_usd,
    ROUND(tdv.volume_usd * 100.0 / NULLIF(tb.total_volume_usd, 0), 2) AS dex_share_pct,
    c.top10_pct                         AS top10_wallets_share_pct,
    tdv.earliest_trade_time,
    tdv.latest_trade_time,
    CASE
        WHEN c.top10_pct > 80 THEN '🐳 Highly Concentrated (Bot/Whale Dominated)'
        WHEN c.top10_pct > 60 THEN '⚠️ Concentrated Trading'
        WHEN c.top10_pct > 40 THEN '📊 Moderate Concentration'
        ELSE '✅ Distributed Trading'
    END                                 AS concentration_signal
FROM token_dex_volume tdv
JOIN total_by_token tb ON tdv.token_address = tb.token_address
JOIN top10_concentration c ON tdv.token_address = c.token_address
ORDER BY tdv.volume_usd DESC
LIMIT 50
