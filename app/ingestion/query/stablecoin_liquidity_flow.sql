-- Stablecoin Liquidity Flow: mint (from=0x0) and burn (to=0x0) events as liquidity signals.
-- Each row = one stablecoin for the current time window.
-- mint_growth_pct compares current window minting to the prior window of the same length.
-- Parameters: {{time_window_hours}}, {{min_usd_value}}

WITH stablecoin_meta AS (
    SELECT contract_address, symbol, decimals FROM (VALUES
        (0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48, 'USDC',  6),
        (0xdAC17F958D2ee523a2206206994597C13D831ec7, 'USDT',  6),
        (0x6B175474E89094C44Da98b954EedeAC495271d0F, 'DAI',  18),
        (0x853d955aCEf822Db058eb8505911ED77F175b99e, 'FRAX', 18),
        (0x6c3ea9036406852006290770BEdFcAbA0e23A0e8, 'PYUSD',  6)
    ) AS t(contract_address, symbol, decimals)
),

all_flows AS (
    SELECT
        sm.symbol,
        CASE
            WHEN tr."from" = 0x0000000000000000000000000000000000000000 THEN 'mint'
            ELSE 'burn'
        END AS flow_type,
        CAST(tr.value AS DOUBLE) / POW(10, sm.decimals) AS token_amount,
        tr."to" AS recipient,
        tr.evt_block_time
    FROM erc20_ethereum.evt_Transfer tr
    INNER JOIN stablecoin_meta sm ON tr.contract_address = sm.contract_address
    WHERE tr.evt_block_time >= NOW() - 2 * INTERVAL '{{time_window_hours}}' HOUR
      AND (
          tr."from" = 0x0000000000000000000000000000000000000000
          OR tr."to" = 0x0000000000000000000000000000000000000000
      )
      AND CAST(tr.value AS DOUBLE) / POW(10, sm.decimals) >= {{min_usd_value}}
),

current_agg AS (
    SELECT
        symbol,
        ROUND(SUM(CASE WHEN flow_type = 'mint' THEN token_amount ELSE 0 END), 2) AS mint_usd,
        ROUND(SUM(CASE WHEN flow_type = 'burn' THEN token_amount ELSE 0 END), 2) AS burn_usd,
        COUNT(DISTINCT CASE WHEN flow_type = 'mint' THEN recipient END) AS new_wallets
    FROM all_flows
    WHERE evt_block_time >= NOW() - INTERVAL '{{time_window_hours}}' HOUR
    GROUP BY symbol
),

prior_agg AS (
    SELECT
        symbol,
        SUM(CASE WHEN flow_type = 'mint' THEN token_amount ELSE 0 END) AS prior_mint_usd
    FROM all_flows
    WHERE evt_block_time < NOW() - INTERVAL '{{time_window_hours}}' HOUR
    GROUP BY symbol
),

preoutput AS (
    SELECT
        c.symbol,
        c.mint_usd,
        c.burn_usd,
        ROUND(c.mint_usd - c.burn_usd, 2) AS net_flow_usd,
        ROUND(c.mint_usd + c.burn_usd, 2) AS total_usd,
        ROUND(
            (c.mint_usd - COALESCE(p.prior_mint_usd, 0)) * 100.0
            / NULLIF(COALESCE(p.prior_mint_usd, 0), 0)
        , 2) AS mint_growth_pct,
        c.new_wallets,
        date_trunc('hour', NOW()) AS time_bucket,
        'liquidity_flow' AS category,
        FILTER(
            ARRAY[
                CASE WHEN c.mint_usd > c.burn_usd THEN 'NET_MINT_PRESSURE' END,
                CASE WHEN c.burn_usd > c.mint_usd THEN 'NET_BURN_PRESSURE' END,
                CASE WHEN c.mint_usd >= 10000000 THEN 'HIGH_MINT_VOLUME' END,
                CASE WHEN ABS(c.mint_usd - c.burn_usd) / NULLIF(c.mint_usd + c.burn_usd, 0) > 0.5
                     THEN 'STRONG_DIRECTIONAL_FLOW' END
            ],
            x -> x IS NOT NULL
        ) AS signals
    FROM current_agg c
    LEFT JOIN prior_agg p ON c.symbol = p.symbol
)

SELECT
    symbol,
    mint_usd,
    burn_usd,
    net_flow_usd,
    total_usd,
    mint_growth_pct,
    new_wallets,
    time_bucket,
    category,
    signals,
    CARDINALITY(signals) AS signal_count
FROM preoutput
ORDER BY total_usd DESC
