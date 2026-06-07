-- Protocol Inflow Leaderboard: Aave v3, EigenLayer, Lido deposits (Flipside / Snowflake)
-- Uses ethereum.core.ez_token_transfers to approximate protocol inflows by
-- detecting deposits into known protocol contract addresses, with price from
-- ethereum.price.ez_prices_hourly.
-- Parameters: {{time_window_hours}}, {{min_usd_value}}, {{end_time}}

WITH protocol_contracts AS (
    SELECT address, protocol, deployment_type FROM (VALUES
        -- Aave v3 Pool
        ('0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2', 'Aave_v3',    'lending'),
        -- EigenLayer StrategyManager
        ('0x858646372cc42e1a627fce94aa7a7033e7cf075a', 'EigenLayer', 'restaking'),
        -- Lido stETH deposit contract
        ('0xae7ab96520de3a18e5e111b5eaab095312d7fe84', 'Lido',       'liquid_staking')
    ) AS t(address, protocol, deployment_type)
),

raw_inflows AS (
    SELECT
        tr.block_timestamp,
        tr.to_address                               AS protocol_address,
        pc.protocol,
        pc.deployment_type,
        tr.from_address                             AS depositor,
        -- Use token amount × hourly price for USD value
        tr.amount * COALESCE(p.price, 0)            AS usd_value
    FROM ethereum.core.ez_token_transfers tr
    JOIN protocol_contracts pc
        ON LOWER(tr.to_address) = pc.address
    LEFT JOIN ethereum.price.ez_prices_hourly p
        ON LOWER(p.token_address) = LOWER(tr.contract_address)
        AND p.hour = DATE_TRUNC('hour', tr.block_timestamp)
    WHERE tr.block_timestamp >= TIMESTAMPADD(HOUR, -2 * {{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
      AND tr.block_timestamp <  '{{end_time}}'::TIMESTAMP_NTZ
      AND tr.amount > 0
),

agg AS (
    SELECT
        protocol                                    AS symbol,
        deployment_type,
        ROUND(SUM(CASE WHEN block_timestamp >= TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
                            AND block_timestamp <  '{{end_time}}'::TIMESTAMP_NTZ
                       THEN usd_value ELSE 0 END), 2)                   AS net_flow_usd,
        ROUND(SUM(CASE WHEN block_timestamp >= TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
                            AND block_timestamp <  '{{end_time}}'::TIMESTAMP_NTZ
                       THEN usd_value ELSE 0 END), 2)                   AS total_usd,
        ROUND(SUM(CASE WHEN block_timestamp >= TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
                            AND block_timestamp <  '{{end_time}}'::TIMESTAMP_NTZ
                            AND usd_value >= {{min_usd_value}}
                       THEN usd_value ELSE 0 END), 2)                   AS whale_usd,
        COUNT(DISTINCT CASE WHEN block_timestamp >= TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
                                 AND block_timestamp <  '{{end_time}}'::TIMESTAMP_NTZ
                            THEN depositor END)                         AS new_wallets,
        ROUND(SUM(CASE WHEN block_timestamp < TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
                       THEN usd_value ELSE 0 END), 2)                   AS prior_usd
    FROM raw_inflows
    WHERE usd_value > 0
    GROUP BY protocol, deployment_type
)

SELECT
    symbol,
    deployment_type,
    net_flow_usd,
    total_usd,
    whale_usd,
    new_wallets,
    ROUND(net_flow_usd / NULLIF(prior_usd, 0), 2)                       AS volume_multiplier,
    '{{end_time}}'::TIMESTAMP_NTZ                                       AS time_bucket,
    'protocol_inflow'                                                   AS category,
    ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN net_flow_usd >= 10000000                               THEN 'HIGH_PROTOCOL_INFLOW'   ELSE NULL END,
        CASE WHEN whale_usd / NULLIF(net_flow_usd, 0) >= 0.5            THEN 'WHALE_DOMINATED'        ELSE NULL END,
        CASE WHEN new_wallets >= 100                                     THEN 'BROAD_ADOPTION'         ELSE NULL END,
        CASE WHEN net_flow_usd / NULLIF(prior_usd, 0) >= 2.0            THEN 'ACCELERATING_INFLOW'    ELSE NULL END
    ))                                                                  AS signals,
    ARRAY_SIZE(ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN net_flow_usd >= 10000000                               THEN 'HIGH_PROTOCOL_INFLOW'   ELSE NULL END,
        CASE WHEN whale_usd / NULLIF(net_flow_usd, 0) >= 0.5            THEN 'WHALE_DOMINATED'        ELSE NULL END,
        CASE WHEN new_wallets >= 100                                     THEN 'BROAD_ADOPTION'         ELSE NULL END,
        CASE WHEN net_flow_usd / NULLIF(prior_usd, 0) >= 2.0            THEN 'ACCELERATING_INFLOW'    ELSE NULL END
    )))                                                                 AS signal_count
FROM agg
ORDER BY net_flow_usd DESC
LIMIT 10
