-- Whale Transaction Filter
-- Large ERC20 transfers for Top 10 tokens filtered by USD value and time window
-- Parameters: {{min_usd_value}} (e.g. 100000 or 500000), {{time_window_hours}} (e.g. 1, 6, 24)

WITH top_tokens AS (
    SELECT
        contract_address,
        symbol,
        decimals
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
        t.evt_block_time                                        AS block_time,
        t.contract_address,
        tk.symbol,
        t."from"                                                AS sender,
        t."to"                                                  AS receiver,
        t.value / POWER(10, COALESCE(tk.decimals, 18))         AS token_amount,
        p.price,
        t.value / POWER(10, COALESCE(tk.decimals, 18)) * p.price AS usd_value,
        t.evt_tx_hash                                           AS tx_hash
    FROM erc20_ethereum.evt_Transfer t
    INNER JOIN top_tokens tk
        ON t.contract_address = tk.contract_address
    LEFT JOIN prices.usd p
        ON p.blockchain = 'ethereum'
       AND p.contract_address = t.contract_address
       AND p.minute = date_trunc('minute', t.evt_block_time)
    WHERE t.evt_block_time >= NOW() - INTERVAL '{{time_window_hours}}' HOUR
)

SELECT
    block_time,
    symbol,
    sender,
    receiver,
    ROUND(token_amount, 4)  AS token_amount,
    ROUND(usd_value, 2)     AS usd_value,
    CASE
        WHEN usd_value >= 500000 THEN '🐋 Mega Whale (>$500k)'
        WHEN usd_value >= 100000 THEN '🐋 Whale (>$100k)'
    END                     AS whale_tier,
    tx_hash,
    'https://etherscan.io/tx/' || CAST(tx_hash AS VARCHAR) AS etherscan_url
FROM transfers
WHERE usd_value >= {{min_usd_value}}
ORDER BY usd_value DESC
LIMIT 200
