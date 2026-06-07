-- Whale Transaction Filter (Flipside / Snowflake)
-- Table: ethereum.core.ez_token_transfers
--   amount_usd is pre-computed; no price join needed.
-- Parameters: {{min_usd_value}}, {{time_window_hours}}, {{end_time}}

WITH filtered AS (
    SELECT
        block_timestamp                                                 AS block_time,
        tx_hash,
        symbol,
        from_address                                                    AS sender,
        to_address                                                      AS receiver,
        ROUND(amount, 4)                                                AS token_amount,
        ROUND(amount_usd, 2)                                            AS usd_value,
        'https://etherscan.io/tx/' || tx_hash                           AS etherscan_url
    FROM ethereum.core.ez_token_transfers
    WHERE block_timestamp >= TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
      AND block_timestamp <  '{{end_time}}'::TIMESTAMP_NTZ
      AND symbol IN ('USDT','USDC','WBTC','WETH','LINK','UNI','AAVE','stETH','DAI','MKR')
      AND amount_usd >= {{min_usd_value}}
      AND amount_usd IS NOT NULL
),

with_aggregates AS (
    SELECT
        block_time,
        symbol,
        sender,
        receiver,
        token_amount,
        usd_value,
        tx_hash,
        ROUND(SUM(usd_value) OVER (PARTITION BY symbol), 2)                        AS total_usd,
        ROUND(SUM(CASE WHEN usd_value >= 100000 THEN usd_value ELSE 0 END)
              OVER (PARTITION BY symbol), 2)                                        AS whale_usd,
        ROUND(SUM(CASE WHEN usd_value >= 500000 THEN usd_value ELSE 0 END)
              OVER (PARTITION BY symbol), 2)                                        AS smart_money_usd,
        etherscan_url
    FROM filtered
)

SELECT
    block_time,
    symbol,
    sender,
    receiver,
    token_amount,
    usd_value,
    total_usd,
    whale_usd,
    smart_money_usd,
    tx_hash,
    etherscan_url,
    '{{end_time}}'::TIMESTAMP_NTZ                                                   AS time_bucket,
    'smart_deployment'                                                              AS category,
    ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN usd_value >= 500000           THEN 'MEGA_WHALE_TX'              ELSE NULL END,
        CASE WHEN usd_value >= 100000
              AND usd_value < 500000            THEN 'WHALE_TX'                   ELSE NULL END,
        CASE WHEN whale_usd / NULLIF(total_usd, 0) > 0.8
                                                THEN 'HIGH_SYMBOL_CONCENTRATION'  ELSE NULL END
    ))                                                                              AS signals,
    ARRAY_SIZE(ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN usd_value >= 500000           THEN 'MEGA_WHALE_TX'              ELSE NULL END,
        CASE WHEN usd_value >= 100000
              AND usd_value < 500000            THEN 'WHALE_TX'                   ELSE NULL END,
        CASE WHEN whale_usd / NULLIF(total_usd, 0) > 0.8
                                                THEN 'HIGH_SYMBOL_CONCENTRATION'  ELSE NULL END
    )))                                                                             AS signal_count
FROM with_aggregates
ORDER BY usd_value DESC
LIMIT 50
