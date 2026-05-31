-- Bridge Activity: Ethereum ↔ L2s
-- Uses bridges_evms.deposits / bridges_evms.withdrawals Spellbook tables
-- Parameters: {{time_window_hours}} (e.g. 1, 6, 24), {{min_usd_value}} (e.g. 10000)

WITH deposits AS (
    -- Capital moving from Ethereum → any L2
    SELECT
        CONCAT('Ethereum → ', withdrawal_chain)   AS direction,
        bridge_name                               AS bridge,
        tx_hash,
        sender,
        deposit_amount_usd                        AS usd_value
    FROM bridges_evms.deposits
    WHERE deposit_chain = 'ethereum'
      AND block_time >= NOW() - INTERVAL '{{time_window_hours}}' HOUR
      AND deposit_amount_usd >= {{min_usd_value}}
),

withdrawals AS (
    -- Capital returning from any L2 → Ethereum
    SELECT
        CONCAT(deposit_chain, ' → Ethereum')      AS direction,
        bridge_name                               AS bridge,
        tx_hash,
        sender,
        withdrawal_amount_usd                     AS usd_value
    FROM bridges_evms.withdrawals
    WHERE withdrawal_chain = 'ethereum'
      AND block_time >= NOW() - INTERVAL '{{time_window_hours}}' HOUR
      AND withdrawal_amount_usd >= {{min_usd_value}}
),

all_flows AS (
    SELECT * FROM deposits
    UNION ALL
    SELECT * FROM withdrawals
)

SELECT
    direction,
    bridge,
    COUNT(*)                    AS tx_count,
    COUNT(DISTINCT sender)      AS unique_wallets,
    CAST(NULL AS DOUBLE)        AS total_eth,
    ROUND(SUM(usd_value), 2)    AS total_usd,
    CASE
        WHEN direction LIKE 'Ethereum →%'
            THEN '🟡 Capital Moving to L2'
        ELSE '🔵 Capital Returning to L1'
    END                         AS capital_signal
FROM all_flows
GROUP BY direction, bridge
ORDER BY total_usd DESC
