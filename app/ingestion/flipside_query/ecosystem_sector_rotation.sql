-- Ecosystem Sector Rotation (Flipside / Snowflake)
-- Parameters: {{time_window_hours}}, {{min_usd_value}}, {{end_time}}

WITH sector_map AS (
    SELECT address, sector FROM (VALUES
        ('0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48', 'Stablecoins'),
        ('0xdac17f958d2ee523a2206206994597c13d831ec7', 'Stablecoins'),
        ('0x6b175474e89094c44da98b954eedeac495271d0f', 'Stablecoins'),
        ('0xae7ab96520de3a18e5e111b5eaab095312d7fe84', 'Liquid_Staking'),
        ('0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0', 'Liquid_Staking'),
        ('0xbe9895146f7af43049ca1c1ae358b0541ea49704', 'Liquid_Staking'),
        ('0xfe2e637202056d30016725477c5da089ab0a043a', 'Restaking'),
        ('0xac3e018457b222d93114458476f3e3416abbe38f', 'Restaking'),
        ('0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9', 'DeFi_Lending'),
        ('0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2', 'DeFi_Lending'),
        ('0xc00e94cb662c3520282e6f5717214004a7f26888', 'DeFi_Lending'),
        ('0x1f9840a85d5af5bf1d1762f925bdaddc4201f984', 'DEX_Governance'),
        ('0xd533a949740bb3306d119cc777fa900ba034cd52', 'DEX_Governance'),
        ('0xba100000625a3754423978a60c9317c58a424e3d', 'DEX_Governance'),
        ('0x514910771af9ca656af840dff83e8264ecf986ca', 'Infrastructure'),
        ('0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2', 'Blue_Chip'),
        ('0x2260fac5e5542a773aa44fbcfedf7c193bc2c599', 'Blue_Chip')
    ) AS t(address, sector)
),

raw_trades AS (
    SELECT
        s.block_timestamp,
        s.amount_out_usd                        AS amount_usd,
        s.origin_from_address                   AS taker,
        COALESCE(s_in.sector,  'Other')         AS sector_bought,
        COALESCE(s_out.sector, 'Other')         AS sector_sold
    FROM ethereum.core.ez_dex_swaps s
    LEFT JOIN sector_map s_in  ON LOWER(s.token_out_address) = s_in.address
    LEFT JOIN sector_map s_out ON LOWER(s.token_in_address)  = s_out.address
    WHERE s.block_timestamp >= TIMESTAMPADD(HOUR, -2 * {{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
      AND s.block_timestamp <  '{{end_time}}'::TIMESTAMP_NTZ
      AND s.amount_out_usd >= {{min_usd_value}}
      AND s.amount_out_usd IS NOT NULL
      AND (s_in.sector IS NOT NULL OR s_out.sector IS NOT NULL)
),

sector_flows AS (
    SELECT block_timestamp, amount_usd, taker, sector_bought AS sector, 'in'  AS direction
    FROM raw_trades WHERE sector_bought != 'Other'
    UNION ALL
    SELECT block_timestamp, amount_usd, taker, sector_sold  AS sector, 'out' AS direction
    FROM raw_trades WHERE sector_sold  != 'Other'
),

current_sector AS (
    SELECT
        sector,
        ROUND(SUM(CASE WHEN direction = 'in'  THEN amount_usd ELSE 0 END), 2) AS gross_inflow_usd,
        ROUND(SUM(CASE WHEN direction = 'out' THEN amount_usd ELSE 0 END), 2) AS gross_outflow_usd,
        COUNT(*) AS trade_count,
        COUNT(DISTINCT taker) AS unique_traders
    FROM sector_flows
    WHERE block_timestamp >= TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
      AND block_timestamp <  '{{end_time}}'::TIMESTAMP_NTZ
    GROUP BY sector
),

prior_sector AS (
    SELECT sector, SUM(amount_usd) AS prior_total_usd
    FROM sector_flows
    WHERE block_timestamp < TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
    GROUP BY sector
),

totals AS (
    SELECT SUM(gross_inflow_usd + gross_outflow_usd) AS grand_total_usd
    FROM current_sector
)

SELECT
    cs.sector                                                                       AS symbol,
    cs.gross_inflow_usd,
    cs.gross_outflow_usd,
    ROUND(cs.gross_inflow_usd - cs.gross_outflow_usd, 2)                            AS net_flow_usd,
    ROUND(cs.gross_inflow_usd + cs.gross_outflow_usd, 2)                            AS total_usd,
    ROUND((cs.gross_inflow_usd + cs.gross_outflow_usd) * 100.0
          / NULLIF(t.grand_total_usd, 0), 2)                                        AS percentage_of_total,
    cs.trade_count,
    cs.unique_traders,
    ROUND((cs.gross_inflow_usd + cs.gross_outflow_usd)
          / NULLIF(COALESCE(ps.prior_total_usd, 0), 0), 2)                          AS volume_multiplier,
    '{{end_time}}'::TIMESTAMP_NTZ                                                   AS time_bucket,
    'sector_rotation'                                                               AS category,
    ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN cs.gross_inflow_usd > cs.gross_outflow_usd * 1.5                          THEN 'STRONG_ROTATION_IN'        ELSE NULL END,
        CASE WHEN cs.gross_outflow_usd > cs.gross_inflow_usd * 1.5                          THEN 'STRONG_ROTATION_OUT'       ELSE NULL END,
        CASE WHEN (cs.gross_inflow_usd + cs.gross_outflow_usd) >= 10000000                  THEN 'HIGH_SECTOR_VOLUME'        ELSE NULL END,
        CASE WHEN (cs.gross_inflow_usd + cs.gross_outflow_usd)
                  / NULLIF(COALESCE(ps.prior_total_usd, 0), 0) > 2.0               THEN 'ACCELERATING_ROTATION'     ELSE NULL END
    ))                                                                              AS signals,
    ARRAY_SIZE(ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN cs.gross_inflow_usd > cs.gross_outflow_usd * 1.5                          THEN 'STRONG_ROTATION_IN'        ELSE NULL END,
        CASE WHEN cs.gross_outflow_usd > cs.gross_inflow_usd * 1.5                          THEN 'STRONG_ROTATION_OUT'       ELSE NULL END,
        CASE WHEN (cs.gross_inflow_usd + cs.gross_outflow_usd) >= 10000000                  THEN 'HIGH_SECTOR_VOLUME'        ELSE NULL END,
        CASE WHEN (cs.gross_inflow_usd + cs.gross_outflow_usd)
                  / NULLIF(COALESCE(ps.prior_total_usd, 0), 0) > 2.0               THEN 'ACCELERATING_ROTATION'     ELSE NULL END
    )))                                                                             AS signal_count
FROM current_sector cs
LEFT JOIN prior_sector ps ON cs.sector = ps.sector
CROSS JOIN totals t
ORDER BY total_usd DESC
LIMIT 10
