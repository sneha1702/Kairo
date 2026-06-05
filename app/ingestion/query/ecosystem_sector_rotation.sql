-- Ecosystem Sector Rotation: DEX buy/sell flows by DeFi sector on Ethereum mainnet.
-- symbol = sector name. Each row = one sector for the current time window.
-- volume_multiplier compares current vs prior period of the same length.
-- Parameters: {{time_window_hours}}, {{min_usd_value}}, {{end_time}}

WITH sector_map AS (
    SELECT address, sector FROM (VALUES
        -- Stablecoins
        (0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48, 'Stablecoins'),
        (0xdAC17F958D2ee523a2206206994597C13D831ec7, 'Stablecoins'),
        (0x6B175474E89094C44Da98b954EedeAC495271d0F, 'Stablecoins'),
        -- Liquid Staking
        (0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84, 'Liquid_Staking'),
        (0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0, 'Liquid_Staking'),
        (0xBe9895146f7AF43049ca1c1AE358B0541Ea49704, 'Liquid_Staking'),
        -- Restaking
        (0xFe2e637202056d30016725477c5da089Ab0A043A, 'Restaking'),
        (0xac3E018457B222d93114458476f3E3416Abbe38F, 'Restaking'),
        -- DeFi Lending
        (0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9, 'DeFi_Lending'),
        (0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2, 'DeFi_Lending'),
        (0xc00e94Cb662C3520282E6f5717214004A7f26888, 'DeFi_Lending'),
        -- DEX Governance
        (0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984, 'DEX_Governance'),
        (0xD533a949740bb3306d119CC777fa900bA034cd52, 'DEX_Governance'),
        (0xba100000625a3754423978a60c9317c58a424e3D, 'DEX_Governance'),
        -- Infrastructure
        (0x514910771AF9Ca656af840dff83E8264EcF986CA, 'Infrastructure'),
        (0x0bc529c00C6401aEF6D220BE8C6Ea1667F6Ad93e, 'Infrastructure'),
        -- Blue Chip
        (0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2, 'Blue_Chip'),
        (0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599, 'Blue_Chip')
    ) AS t(address, sector)
),

raw_trades AS (
    SELECT
        t.block_time,
        t.amount_usd,
        t.taker,
        COALESCE(s_in.sector,  'Other') AS sector_bought,
        COALESCE(s_out.sector, 'Other') AS sector_sold
    FROM dex.trades t
    LEFT JOIN sector_map s_in  ON t.token_bought_address = s_in.address
    LEFT JOIN sector_map s_out ON t.token_sold_address   = s_out.address
    WHERE t.blockchain = 'ethereum'
      AND t.block_time >= TIMESTAMP '{{end_time}}' - 2 * INTERVAL '{{time_window_hours}}' HOUR
      AND t.block_time <  TIMESTAMP '{{end_time}}'
      AND t.amount_usd >= {{min_usd_value}}
      AND (s_in.sector IS NOT NULL OR s_out.sector IS NOT NULL)
),

-- Each trade produces up to two sector-flow rows: inflow to sector_bought, outflow from sector_sold
sector_flows AS (
    SELECT block_time, amount_usd, taker, sector_bought AS sector, 'in'  AS direction
    FROM raw_trades WHERE sector_bought != 'Other'
    UNION ALL
    SELECT block_time, amount_usd, taker, sector_sold  AS sector, 'out' AS direction
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
    WHERE block_time >= TIMESTAMP '{{end_time}}' - INTERVAL '{{time_window_hours}}' HOUR
      AND block_time <  TIMESTAMP '{{end_time}}'
    GROUP BY sector
),

prior_sector AS (
    SELECT
        sector,
        SUM(amount_usd) AS prior_total_usd
    FROM sector_flows
    WHERE block_time < TIMESTAMP '{{end_time}}' - INTERVAL '{{time_window_hours}}' HOUR
    GROUP BY sector
),

totals AS (
    SELECT SUM(gross_inflow_usd + gross_outflow_usd) AS grand_total_usd
    FROM current_sector
),

preoutput AS (
    SELECT
        cs.sector AS symbol,
        cs.gross_inflow_usd,
        cs.gross_outflow_usd,
        ROUND(cs.gross_inflow_usd - cs.gross_outflow_usd, 2) AS net_flow_usd,
        ROUND(cs.gross_inflow_usd + cs.gross_outflow_usd, 2) AS total_usd,
        ROUND(
            (cs.gross_inflow_usd + cs.gross_outflow_usd) * 100.0
            / NULLIF(t.grand_total_usd, 0)
        , 2) AS percentage_of_total,
        cs.trade_count,
        cs.unique_traders,
        ROUND(
            (cs.gross_inflow_usd + cs.gross_outflow_usd)
            / NULLIF(COALESCE(ps.prior_total_usd, 0), 0)
        , 2) AS volume_multiplier,
        TIMESTAMP '{{end_time}}' AS time_bucket,
        'sector_rotation' AS category,
        FILTER(
            ARRAY[
                CASE WHEN cs.gross_inflow_usd > cs.gross_outflow_usd * 1.5
                     THEN 'STRONG_ROTATION_IN' END,
                CASE WHEN cs.gross_outflow_usd > cs.gross_inflow_usd * 1.5
                     THEN 'STRONG_ROTATION_OUT' END,
                CASE WHEN (cs.gross_inflow_usd + cs.gross_outflow_usd) >= 10000000
                     THEN 'HIGH_SECTOR_VOLUME' END,
                CASE WHEN (cs.gross_inflow_usd + cs.gross_outflow_usd)
                          / NULLIF(COALESCE(ps.prior_total_usd, 0), 0) > 2.0
                     THEN 'ACCELERATING_ROTATION' END
            ],
            x -> x IS NOT NULL
        ) AS signals
    FROM current_sector cs
    LEFT JOIN prior_sector ps ON cs.sector = ps.sector
    CROSS JOIN totals t
)

SELECT
    symbol,
    gross_inflow_usd,
    gross_outflow_usd,
    net_flow_usd,
    total_usd,
    percentage_of_total,
    trade_count,
    unique_traders,
    volume_multiplier,
    time_bucket,
    category,
    signals,
    CARDINALITY(signals) AS signal_count
FROM preoutput
ORDER BY total_usd DESC
