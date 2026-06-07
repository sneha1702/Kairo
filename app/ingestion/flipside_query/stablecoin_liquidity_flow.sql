-- Stablecoin Liquidity Flow (Flipside / Snowflake)
-- Mint = transfer from 0x0 address; Burn = transfer to 0x0 address.
-- Parameters: {{time_window_hours}}, {{min_usd_value}}, {{end_time}}

WITH all_flows AS (
    SELECT
        symbol,
        CASE WHEN from_address = '0x0000000000000000000000000000000000000000' THEN 'mint'
             ELSE 'burn'
        END                                     AS flow_type,
        amount                                  AS token_amount,
        to_address                              AS recipient,
        block_timestamp
    FROM ethereum.core.ez_token_transfers
    WHERE block_timestamp >= TIMESTAMPADD(HOUR, -2 * {{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
      AND block_timestamp <  '{{end_time}}'::TIMESTAMP_NTZ
      AND symbol IN ('USDC','USDT','DAI','FRAX','PYUSD')
      AND (
          from_address = '0x0000000000000000000000000000000000000000'
          OR to_address = '0x0000000000000000000000000000000000000000'
      )
      AND amount >= {{min_usd_value}}
),

current_agg AS (
    SELECT
        symbol,
        ROUND(SUM(CASE WHEN flow_type = 'mint' THEN token_amount ELSE 0 END), 2) AS mint_usd,
        ROUND(SUM(CASE WHEN flow_type = 'burn' THEN token_amount ELSE 0 END), 2) AS burn_usd,
        COUNT(DISTINCT CASE WHEN flow_type = 'mint' THEN recipient END)          AS new_wallets
    FROM all_flows
    WHERE block_timestamp >= TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
      AND block_timestamp <  '{{end_time}}'::TIMESTAMP_NTZ
    GROUP BY symbol
),

prior_agg AS (
    SELECT
        symbol,
        SUM(CASE WHEN flow_type = 'mint' THEN token_amount ELSE 0 END) AS prior_mint_usd
    FROM all_flows
    WHERE block_timestamp < TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
    GROUP BY symbol
)

SELECT
    c.symbol,
    c.mint_usd,
    c.burn_usd,
    ROUND(c.mint_usd - c.burn_usd, 2)                                               AS net_flow_usd,
    ROUND(c.mint_usd + c.burn_usd, 2)                                               AS total_usd,
    ROUND((c.mint_usd - COALESCE(p.prior_mint_usd, 0)) * 100.0
          / NULLIF(COALESCE(p.prior_mint_usd, 0), 0), 2)                            AS mint_growth_pct,
    c.new_wallets,
    '{{end_time}}'::TIMESTAMP_NTZ                                                   AS time_bucket,
    'liquidity_flow'                                                                AS category,
    ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN c.mint_usd > c.burn_usd                                                   THEN 'NET_MINT_PRESSURE'         ELSE NULL END,
        CASE WHEN c.burn_usd > c.mint_usd                                                   THEN 'NET_BURN_PRESSURE'         ELSE NULL END,
        CASE WHEN c.mint_usd >= 10000000                                                    THEN 'HIGH_MINT_VOLUME'          ELSE NULL END,
        CASE WHEN ABS(c.mint_usd - c.burn_usd) / NULLIF(c.mint_usd + c.burn_usd, 0) > 0.5 THEN 'STRONG_DIRECTIONAL_FLOW'  ELSE NULL END
    ))                                                                              AS signals,
    ARRAY_SIZE(ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN c.mint_usd > c.burn_usd                                                   THEN 'NET_MINT_PRESSURE'         ELSE NULL END,
        CASE WHEN c.burn_usd > c.mint_usd                                                   THEN 'NET_BURN_PRESSURE'         ELSE NULL END,
        CASE WHEN c.mint_usd >= 10000000                                                    THEN 'HIGH_MINT_VOLUME'          ELSE NULL END,
        CASE WHEN ABS(c.mint_usd - c.burn_usd) / NULLIF(c.mint_usd + c.burn_usd, 0) > 0.5 THEN 'STRONG_DIRECTIONAL_FLOW'  ELSE NULL END
    )))                                                                             AS signal_count
FROM current_agg c
LEFT JOIN prior_agg p ON c.symbol = p.symbol
ORDER BY total_usd DESC
LIMIT 10
