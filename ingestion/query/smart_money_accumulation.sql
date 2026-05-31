-- Smart Money Accumulation
-- Tracks wallets making multiple large DEX buys of a token within the time window.
-- (Removed labels.all dependency — not available on free tier.)
-- (Replaced EXTRACT(EPOCH...) with date_diff — not supported in DuneSQL.)
-- Parameters: {{token_address}}, {{time_window_hours}} (e.g. 1, 6, 24), {{min_buy_usd}} (e.g. 10000)

WITH recent_buys AS (
    SELECT
        t.block_time,
        t.taker                         AS wallet,
        t.token_bought_symbol           AS symbol,
        t.amount_usd,
        t.tx_hash
    FROM dex.trades t
    WHERE t.blockchain = 'ethereum'
      AND t.block_time >= NOW() - INTERVAL '{{time_window_hours}}' HOUR
      AND t.token_bought_address = {{token_address}}
      AND t.amount_usd >= {{min_buy_usd}}
),

wallet_stats AS (
    SELECT
        wallet,
        symbol,
        COUNT(*)                                            AS buy_count,
        ROUND(SUM(amount_usd), 2)                           AS total_bought_usd,
        MIN(block_time)                                     AS first_buy,
        MAX(block_time)                                     AS last_buy,
        ROUND(
            CAST(date_diff('minute', MIN(block_time), MAX(block_time)) AS DOUBLE), 1
        )                                                   AS time_span_minutes
    FROM recent_buys
    GROUP BY wallet, symbol
    HAVING COUNT(*) >= 2
),

net_pressure AS (
    SELECT
        token_bought_symbol             AS symbol,
        ROUND(SUM(amount_usd), 2)       AS total_smart_money_flow_usd,
        COUNT(DISTINCT taker)           AS wallets_buying_same_token
    FROM dex.trades
    WHERE blockchain = 'ethereum'
      AND block_time >= NOW() - INTERVAL '{{time_window_hours}}' HOUR
      AND token_bought_address = {{token_address}}
    GROUP BY token_bought_symbol
)

SELECT
    ws.wallet,
    ws.symbol,
    ws.buy_count,
    ws.total_bought_usd,
    ws.first_buy,
    ws.last_buy,
    ws.time_span_minutes,
    CASE
        WHEN ws.buy_count >= 3 AND ws.time_span_minutes <= 60  THEN '🔥 Aggressive Accumulation'
        WHEN ws.buy_count >= 2                                 THEN '📈 Building Position'
        ELSE '👀 Single Large Buy'
    END                             AS accumulation_signal,
    np.total_smart_money_flow_usd,
    np.wallets_buying_same_token
FROM wallet_stats ws
JOIN net_pressure np ON ws.symbol = np.symbol
ORDER BY ws.total_bought_usd DESC
LIMIT 100
