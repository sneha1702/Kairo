-- Smart Money Accumulation: Per-symbol summary of sophisticated capital activity.
-- Qualifies wallets that make ≥2 buys above {{min_buy_usd}} within the window.
-- Parameters: {{token_address}}, {{time_window_hours}}, {{min_buy_usd}}, {{end_time}}

WITH recent_buys AS (
    SELECT
        t.block_time,
        t.taker              AS wallet,
        t.token_bought_symbol AS symbol,
        t.amount_usd,
        t.tx_hash
    FROM dex.trades t
    WHERE t.blockchain = 'ethereum'
      AND t.block_time >= TIMESTAMP '{{end_time}}' - INTERVAL '{{time_window_hours}}' HOUR
      AND t.block_time <  TIMESTAMP '{{end_time}}'
      AND t.token_bought_address = {{token_address}}
      AND t.amount_usd >= {{min_buy_usd}}
),

-- Per-wallet stats; only include wallets with ≥2 qualifying buys (smart money proxy)
wallet_stats AS (
    SELECT
        wallet,
        symbol,
        COUNT(*)                                                    AS buy_count,
        ROUND(SUM(amount_usd), 2)                                   AS total_bought_usd,
        ROUND(
            CAST(date_diff('minute', MIN(block_time), MAX(block_time)) AS DOUBLE), 1
        )                                                           AS time_span_minutes
    FROM recent_buys
    GROUP BY wallet, symbol
    HAVING COUNT(*) >= 2
),

-- Top-10 wallets by buy volume — proxy for smart money concentration
top10_share AS (
    SELECT COALESCE(SUM(total_bought_usd), 0) AS top10_usd
    FROM (
        SELECT total_bought_usd
        FROM wallet_stats
        ORDER BY total_bought_usd DESC
        LIMIT 10
    ) top10
),

-- Token-level aggregates from qualifying wallets
token_level AS (
    SELECT
        symbol,
        COUNT(*)                                                               AS wallet_count,
        ROUND(SUM(total_bought_usd), 2)                                        AS smart_money_usd,
        ROUND(SUM(CASE WHEN total_bought_usd >= 100000 THEN total_bought_usd
                       ELSE 0 END), 2)                                         AS whale_usd
    FROM wallet_stats
    GROUP BY symbol
),

-- DEX sells of the same token in the same window (any size)
recent_sells AS (
    SELECT
        t.token_sold_symbol AS symbol,
        ROUND(SUM(t.amount_usd), 2) AS total_sell_usd
    FROM dex.trades t
    WHERE t.blockchain = 'ethereum'
      AND t.block_time >= TIMESTAMP '{{end_time}}' - INTERVAL '{{time_window_hours}}' HOUR
      AND t.block_time <  TIMESTAMP '{{end_time}}'
      AND t.token_sold_address = {{token_address}}
    GROUP BY t.token_sold_symbol
),

net_pressure AS (
    SELECT
        token_bought_symbol           AS symbol,
        ROUND(SUM(amount_usd), 2)     AS total_buy_usd,
        COUNT(DISTINCT taker)         AS wallets_buying_same_token
    FROM dex.trades
    WHERE blockchain = 'ethereum'
      AND block_time >= TIMESTAMP '{{end_time}}' - INTERVAL '{{time_window_hours}}' HOUR
      AND block_time <  TIMESTAMP '{{end_time}}'
      AND token_bought_address = {{token_address}}
    GROUP BY token_bought_symbol
),

preoutput AS (
    SELECT
        tl.symbol,
        tl.smart_money_usd,
        tl.whale_usd,
        ROUND(tl.smart_money_usd - COALESCE(rs.total_sell_usd, 0), 2)          AS net_flow_usd,
        ROUND(t10.top10_usd * 100.0 / NULLIF(tl.smart_money_usd, 0), 2)        AS smart_money_concentration_pct,
        tl.wallet_count,
        np.total_buy_usd                                                        AS total_smart_money_flow_usd,
        np.wallets_buying_same_token,
        TIMESTAMP '{{end_time}}'                                                AS time_bucket,
        'smart_deployment'                                                      AS category,
        FILTER(
            ARRAY[
                CASE WHEN tl.smart_money_usd > 500000
                     THEN 'LARGE_SMART_MONEY_FLOW' END,
                CASE WHEN tl.whale_usd > 0
                     THEN 'WHALE_ACCUMULATION' END,
                CASE WHEN (tl.smart_money_usd - COALESCE(rs.total_sell_usd, 0)) > 0
                     THEN 'NET_BUYING_PRESSURE' END,
                CASE WHEN t10.top10_usd * 100.0 / NULLIF(tl.smart_money_usd, 0) > 70
                     THEN 'HIGH_SMART_MONEY_CONCENTRATION' END
            ],
            x -> x IS NOT NULL
        )                                                                       AS signals
    FROM token_level tl
    JOIN net_pressure np     ON tl.symbol = np.symbol
    LEFT JOIN recent_sells rs ON tl.symbol = rs.symbol
    CROSS JOIN top10_share t10
)

SELECT
    symbol,
    smart_money_usd,
    whale_usd,
    net_flow_usd,
    smart_money_concentration_pct,
    wallet_count,
    total_smart_money_flow_usd,
    wallets_buying_same_token,
    time_bucket,
    category,
    signals,
    CARDINALITY(signals) AS signal_count
FROM preoutput
