-- Wallet Concentration: Top-50 holder supply share (Flipside / Snowflake)
-- Computes current balances from all historical transfers for {{token_address}}.
-- Parameters: {{token_address}}, {{end_time}}

WITH token_info AS (
    SELECT symbol, decimals
    FROM ethereum.core.dim_contracts
    WHERE LOWER(address) = LOWER('{{token_address}}')
    LIMIT 1
),

wallet_balances AS (
    SELECT
        address,
        SUM(delta) AS balance
    FROM (
        SELECT to_address AS address,
               amount     AS delta
        FROM ethereum.core.ez_token_transfers
        WHERE LOWER(contract_address) = LOWER('{{token_address}}')
          AND block_timestamp < '{{end_time}}'::TIMESTAMP_NTZ

        UNION ALL

        SELECT from_address AS address,
               -amount      AS delta
        FROM ethereum.core.ez_token_transfers
        WHERE LOWER(contract_address) = LOWER('{{token_address}}')
          AND block_timestamp < '{{end_time}}'::TIMESTAMP_NTZ
    ) deltas
    GROUP BY address
    HAVING SUM(delta) > 0
),

total_supply AS (
    SELECT SUM(balance) AS supply
    FROM wallet_balances
    WHERE address != '0x0000000000000000000000000000000000000000'
),

ranked_wallets AS (
    SELECT
        wb.address,
        'Unknown'                                               AS label,
        'wallet'                                                AS address_type,
        wb.balance,
        wb.balance / ts.supply * 100                            AS pct_of_supply,
        ROW_NUMBER() OVER (ORDER BY wb.balance DESC)            AS rank
    FROM wallet_balances wb
    CROSS JOIN total_supply ts
    WHERE wb.address != '0x0000000000000000000000000000000000000000'
),

concentration_summary AS (
    SELECT
        ROUND(SUM(CASE WHEN rank <= 50 THEN pct_of_supply ELSE 0 END), 2) AS whale_concentration_pct,
        ROUND(SUM(CASE WHEN rank <= 10 THEN pct_of_supply ELSE 0 END), 2) AS smart_money_concentration_pct
    FROM ranked_wallets
)

SELECT
    ti.symbol,
    rw.rank,
    rw.address,
    rw.label,
    rw.address_type,
    ROUND(rw.balance, 4)                                                        AS balance,
    ROUND(rw.pct_of_supply, 4)                                                  AS pct_of_supply,
    ROUND(SUM(rw.pct_of_supply) OVER (ORDER BY rw.rank), 2)                     AS cumulative_pct,
    cs.whale_concentration_pct,
    cs.smart_money_concentration_pct,
    CURRENT_TIMESTAMP()                                                         AS snapshot_time,
    '{{end_time}}'::TIMESTAMP_NTZ                                               AS time_bucket,
    'smart_deployment'                                                          AS category,
    ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN cs.whale_concentration_pct > 80              THEN 'EXTREME_WHALE_CONCENTRATION'  ELSE NULL END,
        CASE WHEN cs.whale_concentration_pct BETWEEN 60 AND 80 THEN 'HIGH_WHALE_CONCENTRATION'     ELSE NULL END,
        CASE WHEN cs.smart_money_concentration_pct > 50        THEN 'SMART_MONEY_DOMINANT'         ELSE NULL END,
        CASE WHEN cs.whale_concentration_pct < 40              THEN 'DISTRIBUTED_HOLDINGS'         ELSE NULL END
    ))                                                                          AS signals,
    ARRAY_SIZE(ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN cs.whale_concentration_pct > 80              THEN 'EXTREME_WHALE_CONCENTRATION'  ELSE NULL END,
        CASE WHEN cs.whale_concentration_pct BETWEEN 60 AND 80 THEN 'HIGH_WHALE_CONCENTRATION'     ELSE NULL END,
        CASE WHEN cs.smart_money_concentration_pct > 50        THEN 'SMART_MONEY_DOMINANT'         ELSE NULL END,
        CASE WHEN cs.whale_concentration_pct < 40              THEN 'DISTRIBUTED_HOLDINGS'         ELSE NULL END
    )))                                                                         AS signal_count
FROM ranked_wallets rw
CROSS JOIN concentration_summary cs
CROSS JOIN token_info ti
WHERE rw.rank <= 50
ORDER BY rw.rank
