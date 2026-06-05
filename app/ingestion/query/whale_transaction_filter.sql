-- Whale Transaction Filter: Large ERC20 transfers with per-symbol aggregate context.
-- whale_usd / smart_money_usd / total_usd are per-symbol window aggregates on each row.
-- Parameters: {{min_usd_value}}, {{time_window_hours}}, {{end_time}}

WITH top_tokens AS (
    SELECT contract_address, symbol, decimals
    FROM tokens.erc20
    WHERE blockchain = 'ethereum'
      AND contract_address IN (
          0xdAC17F958D2ee523a2206206994597C13D831ec7,  -- USDT
          0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48,  -- USDC
          0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599,  -- WBTC
          0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2,  -- WETH
          0x514910771AF9Ca656af840dff83E8264EcF986CA,  -- LINK
          0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984,  -- UNI
          0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9,  -- AAVE
          0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84,  -- stETH
          0x6B175474E89094C44Da98b954EedeAC495271d0F,  -- DAI
          0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2   -- MKR
      )
),

transfers AS (
    SELECT
        t.evt_block_time                                         AS block_time,
        t.contract_address,
        tk.symbol,
        t."from"                                                 AS sender,
        t."to"                                                   AS receiver,
        t.value / POWER(10, COALESCE(tk.decimals, 18))          AS token_amount,
        p.price,
        t.value / POWER(10, COALESCE(tk.decimals, 18)) * p.price AS usd_value,
        t.evt_tx_hash                                            AS tx_hash
    FROM erc20_ethereum.evt_Transfer t
    INNER JOIN top_tokens tk ON t.contract_address = tk.contract_address
    LEFT JOIN prices.usd p
        ON p.blockchain = 'ethereum'
       AND p.contract_address = t.contract_address
       AND p.minute = date_trunc('minute', t.evt_block_time)
    WHERE t.evt_block_time >= TIMESTAMP '{{end_time}}' - INTERVAL '{{time_window_hours}}' HOUR
      AND t.evt_block_time <  TIMESTAMP '{{end_time}}'
),

-- Add per-symbol aggregates via window functions
with_aggregates AS (
    SELECT
        block_time,
        symbol,
        sender,
        receiver,
        ROUND(token_amount, 4)                                                         AS token_amount,
        ROUND(usd_value, 2)                                                            AS usd_value,
        tx_hash,
        ROUND(SUM(usd_value) OVER (PARTITION BY symbol), 2)                           AS total_usd,
        ROUND(SUM(CASE WHEN usd_value >= 100000 THEN usd_value ELSE 0 END)
              OVER (PARTITION BY symbol), 2)                                           AS whale_usd,
        ROUND(SUM(CASE WHEN usd_value >= 500000 THEN usd_value ELSE 0 END)
              OVER (PARTITION BY symbol), 2)                                           AS smart_money_usd,
        'https://etherscan.io/tx/' || CAST(tx_hash AS VARCHAR)                         AS etherscan_url
    FROM transfers
    WHERE usd_value >= {{min_usd_value}}
),

preoutput AS (
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
        date_trunc('hour', NOW())                                                      AS time_bucket,
        'smart_deployment'                                                             AS category,
        FILTER(
            ARRAY[
                CASE WHEN usd_value >= 500000 THEN 'MEGA_WHALE_TX' END,
                CASE WHEN usd_value >= 100000 AND usd_value < 500000 THEN 'WHALE_TX' END,
                CASE WHEN whale_usd / NULLIF(total_usd, 0) > 0.8
                     THEN 'HIGH_SYMBOL_CONCENTRATION' END
            ],
            x -> x IS NOT NULL
        )                                                                              AS signals
    FROM with_aggregates
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
    time_bucket,
    category,
    signals,
    CARDINALITY(signals) AS signal_count
FROM preoutput
ORDER BY usd_value DESC
LIMIT 200
