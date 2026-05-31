-- Wallet Concentration: Top 50 Wallets % of Supply
-- Shows how concentrated a token's holdings are among top wallets
-- Parameters: {{token_address}}

WITH token_info AS (
    SELECT
        contract_address,
        symbol,
        decimals
    FROM tokens.erc20
    WHERE blockchain = 'ethereum'
      AND contract_address = {{token_address}}
    LIMIT 1
),

-- Calculate current balance per wallet via net transfers
wallet_balances AS (
    SELECT
        address,
        SUM(delta) AS balance
    FROM (
        -- Incoming transfers
        SELECT
            t."to" AS address,
            CAST(t.value AS DOUBLE) / POWER(10, ti.decimals) AS delta
        FROM erc20_ethereum.evt_Transfer t
        CROSS JOIN token_info ti
        WHERE t.contract_address = {{token_address}}

        UNION ALL

        -- Outgoing transfers
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
    WHERE address != 0x0000000000000000000000000000000000000000  -- exclude burn
),

ranked_wallets AS (
    -- labels.all is unavailable on the free tier; label/type default to Unknown/wallet
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
)

SELECT
    rank,
    address,
    COALESCE(label, 'Unknown')                          AS label,
    COALESCE(address_type, 'wallet')                    AS address_type,
    ROUND(balance, 4)                                   AS balance,
    ROUND(pct_of_supply, 4)                             AS pct_of_supply,
    ROUND(SUM(pct_of_supply) OVER (ORDER BY rank), 2)   AS cumulative_pct,
    CURRENT_TIMESTAMP                                   AS snapshot_time
FROM ranked_wallets
WHERE rank <= 50
ORDER BY rank
