-- Wallet Concentration: Top-50 holder supply share per token.
-- whale_concentration_pct  = top-50 wallets' cumulative supply share.
-- smart_money_concentration_pct = top-10 wallets' cumulative supply share (proxy).
-- Parameters: {{token_address}}, {{end_time}}

WITH token_info AS (
    SELECT contract_address, symbol, decimals
    FROM tokens.erc20
    WHERE blockchain = 'ethereum'
      AND contract_address = {{token_address}}
    LIMIT 1
),

wallet_balances AS (
    SELECT address, SUM(delta) AS balance
    FROM (
        SELECT
            t."to"  AS address,
            CAST(t.value AS DOUBLE) / POWER(10, ti.decimals) AS delta
        FROM erc20_ethereum.evt_Transfer t
        CROSS JOIN token_info ti
        WHERE t.contract_address = {{token_address}}

        UNION ALL

        SELECT
            t."from" AS address,
            -CAST(t.value AS DOUBLE) / POWER(10, ti.decimals) AS delta
        FROM erc20_ethereum.evt_Transfer t
        CROSS JOIN token_info ti
        WHERE t.contract_address = {{token_address}}
    ) deltas
    GROUP BY address
    HAVING SUM(delta) > 0
),

total_supply AS (
    SELECT SUM(balance) AS supply
    FROM wallet_balances
    WHERE address != 0x0000000000000000000000000000000000000000
),

ranked_wallets AS (
    SELECT
        wb.address,
        'Unknown'                                       AS label,
        'wallet'                                        AS address_type,
        wb.balance,
        wb.balance / ts.supply * 100                    AS pct_of_supply,
        ROW_NUMBER() OVER (ORDER BY wb.balance DESC)    AS rank
    FROM wallet_balances wb
    CROSS JOIN total_supply ts
    WHERE wb.address != 0x0000000000000000000000000000000000000000
),

-- Summary concentration metrics
concentration_summary AS (
    SELECT
        ROUND(SUM(CASE WHEN rank <= 50 THEN pct_of_supply ELSE 0 END), 2) AS whale_concentration_pct,
        ROUND(SUM(CASE WHEN rank <= 10 THEN pct_of_supply ELSE 0 END), 2) AS smart_money_concentration_pct
    FROM ranked_wallets
),

preoutput AS (
    SELECT
        ti.symbol,
        rw.rank,
        rw.address,
        rw.label,
        rw.address_type,
        ROUND(rw.balance, 4)                                          AS balance,
        ROUND(rw.pct_of_supply, 4)                                    AS pct_of_supply,
        ROUND(SUM(rw.pct_of_supply) OVER (ORDER BY rw.rank), 2)       AS cumulative_pct,
        cs.whale_concentration_pct,
        cs.smart_money_concentration_pct,
        CURRENT_TIMESTAMP                                             AS snapshot_time,
        date_trunc('hour', NOW())                                     AS time_bucket,
        'smart_deployment'                                            AS category,
        FILTER(
            ARRAY[
                CASE WHEN cs.whale_concentration_pct > 80
                     THEN 'EXTREME_WHALE_CONCENTRATION' END,
                CASE WHEN cs.whale_concentration_pct BETWEEN 60 AND 80
                     THEN 'HIGH_WHALE_CONCENTRATION' END,
                CASE WHEN cs.smart_money_concentration_pct > 50
                     THEN 'SMART_MONEY_DOMINANT' END,
                CASE WHEN cs.whale_concentration_pct < 40
                     THEN 'DISTRIBUTED_HOLDINGS' END
            ],
            x -> x IS NOT NULL
        )                                                             AS signals
    FROM ranked_wallets rw
    CROSS JOIN concentration_summary cs
    CROSS JOIN token_info ti
    WHERE rw.rank <= 50
)

SELECT
    symbol,
    rank,
    address,
    label,
    address_type,
    balance,
    pct_of_supply,
    cumulative_pct,
    whale_concentration_pct,
    smart_money_concentration_pct,
    snapshot_time,
    time_bucket,
    category,
    signals,
    CARDINALITY(signals) AS signal_count
FROM preoutput
ORDER BY rank
