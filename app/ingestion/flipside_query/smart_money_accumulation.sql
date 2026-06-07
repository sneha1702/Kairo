-- Smart Money Accumulation (Flipside / Snowflake)
-- Table: ethereum.core.ez_dex_swaps
--   origin_from_address = EOA that initiated the swap (= taker/trader)
--   amount_in_usd / amount_out_usd pre-computed
-- Parameters: {{token_address}}, {{time_window_hours}}, {{min_buy_usd}}, {{end_time}}

WITH recent_buys AS (
    SELECT
        block_timestamp                         AS block_time,
        origin_from_address                     AS wallet,
        token_out_symbol                        AS symbol,
        amount_out_usd                          AS amount_usd,
        tx_hash
    FROM ethereum.core.ez_dex_swaps
    WHERE block_timestamp >= TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
      AND block_timestamp <  '{{end_time}}'::TIMESTAMP_NTZ
      AND LOWER(token_out_address) = LOWER('{{token_address}}')
      AND amount_out_usd >= {{min_buy_usd}}
      AND amount_out_usd IS NOT NULL
),

wallet_stats AS (
    SELECT
        wallet,
        symbol,
        COUNT(*)                                AS buy_count,
        ROUND(SUM(amount_usd), 2)               AS total_bought_usd,
        ROUND(
            DATEDIFF('minute', MIN(block_time), MAX(block_time))::FLOAT, 1
        )                                       AS time_span_minutes
    FROM recent_buys
    GROUP BY wallet, symbol
    HAVING COUNT(*) >= 2
),

top10_share AS (
    SELECT COALESCE(SUM(total_bought_usd), 0) AS top10_usd
    FROM (
        SELECT total_bought_usd
        FROM wallet_stats
        ORDER BY total_bought_usd DESC
        LIMIT 10
    ) t
),

token_level AS (
    SELECT
        symbol,
        COUNT(*)                                                        AS wallet_count,
        ROUND(SUM(total_bought_usd), 2)                                 AS smart_money_usd,
        ROUND(SUM(CASE WHEN total_bought_usd >= 100000 THEN total_bought_usd ELSE 0 END), 2)
                                                                        AS whale_usd
    FROM wallet_stats
    GROUP BY symbol
),

recent_sells AS (
    SELECT
        token_in_symbol                         AS symbol,
        ROUND(SUM(amount_in_usd), 2)            AS total_sell_usd
    FROM ethereum.core.ez_dex_swaps
    WHERE block_timestamp >= TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
      AND block_timestamp <  '{{end_time}}'::TIMESTAMP_NTZ
      AND LOWER(token_in_address) = LOWER('{{token_address}}')
      AND amount_in_usd IS NOT NULL
    GROUP BY token_in_symbol
),

net_pressure AS (
    SELECT
        token_out_symbol                        AS symbol,
        ROUND(SUM(amount_out_usd), 2)           AS total_buy_usd,
        COUNT(DISTINCT origin_from_address)     AS wallets_buying_same_token
    FROM ethereum.core.ez_dex_swaps
    WHERE block_timestamp >= TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
      AND block_timestamp <  '{{end_time}}'::TIMESTAMP_NTZ
      AND LOWER(token_out_address) = LOWER('{{token_address}}')
      AND amount_out_usd IS NOT NULL
    GROUP BY token_out_symbol
)

SELECT
    tl.symbol,
    tl.smart_money_usd,
    tl.whale_usd,
    ROUND(tl.smart_money_usd - COALESCE(rs.total_sell_usd, 0), 2)      AS net_flow_usd,
    ROUND(t10.top10_usd * 100.0 / NULLIF(tl.smart_money_usd, 0), 2)    AS smart_money_concentration_pct,
    tl.wallet_count,
    np.total_buy_usd                                                    AS total_smart_money_flow_usd,
    np.wallets_buying_same_token,
    '{{end_time}}'::TIMESTAMP_NTZ                                       AS time_bucket,
    'smart_deployment'                                                  AS category,
    ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN tl.smart_money_usd > 500000                           THEN 'LARGE_SMART_MONEY_FLOW'          ELSE NULL END,
        CASE WHEN tl.whale_usd > 0                                      THEN 'WHALE_ACCUMULATION'              ELSE NULL END,
        CASE WHEN (tl.smart_money_usd - COALESCE(rs.total_sell_usd,0)) > 0
                                                                        THEN 'NET_BUYING_PRESSURE'             ELSE NULL END,
        CASE WHEN t10.top10_usd * 100.0 / NULLIF(tl.smart_money_usd,0) > 70
                                                                        THEN 'HIGH_SMART_MONEY_CONCENTRATION'  ELSE NULL END
    ))                                                                  AS signals,
    ARRAY_SIZE(ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN tl.smart_money_usd > 500000                           THEN 'LARGE_SMART_MONEY_FLOW'          ELSE NULL END,
        CASE WHEN tl.whale_usd > 0                                      THEN 'WHALE_ACCUMULATION'              ELSE NULL END,
        CASE WHEN (tl.smart_money_usd - COALESCE(rs.total_sell_usd,0)) > 0
                                                                        THEN 'NET_BUYING_PRESSURE'             ELSE NULL END,
        CASE WHEN t10.top10_usd * 100.0 / NULLIF(tl.smart_money_usd,0) > 70
                                                                        THEN 'HIGH_SMART_MONEY_CONCENTRATION'  ELSE NULL END
    )))                                                                 AS signal_count
FROM token_level tl
JOIN net_pressure np     ON tl.symbol = np.symbol
LEFT JOIN recent_sells rs ON tl.symbol = rs.symbol
CROSS JOIN top10_share t10
