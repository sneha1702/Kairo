-- Post-Bridge Deployment (Flipside / Snowflake)
-- Bridge recipients who then deploy capital to DEX on destination chain.
-- Parameters: {{time_window_hours}}, {{min_usd_value}}, {{end_time}}

WITH bridge_recipients AS (
    SELECT
        LOWER(destination_chain)                AS dest_chain,
        LOWER(to_address)                       AS recipient,
        SUM(amount_usd)                         AS bridged_usd
    FROM crosschain.core.ez_bridge_activity
    WHERE block_timestamp >= TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
      AND block_timestamp <  '{{end_time}}'::TIMESTAMP_NTZ
      AND amount_usd >= {{min_usd_value}}
      AND to_address IS NOT NULL
    GROUP BY LOWER(destination_chain), LOWER(to_address)
),

dex_deployments AS (
    SELECT
        'ethereum'                              AS chain,
        LOWER(s.origin_from_address)            AS deployer,
        COALESCE(s.token_out_symbol, 'UNKNOWN') AS symbol,
        s.amount_out_usd                        AS deployed_usd,
        COALESCE(s.platform, 'unknown_dex')     AS protocol,
        'dex'                                   AS deployment_type
    FROM ethereum.core.ez_dex_swaps s
    INNER JOIN bridge_recipients br
        ON LOWER(s.origin_from_address) = br.recipient
        AND br.dest_chain = 'ethereum'
    WHERE s.block_timestamp >= TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
      AND s.block_timestamp <  '{{end_time}}'::TIMESTAMP_NTZ
      AND s.amount_out_usd >= 1000
      AND s.amount_out_usd IS NOT NULL
),

agg AS (
    SELECT
        symbol,
        chain,
        deployment_type,
        protocol,
        ROUND(SUM(deployed_usd), 2)             AS net_flow_usd,
        ROUND(SUM(deployed_usd), 2)             AS total_usd,
        COUNT(DISTINCT deployer)                AS new_wallets,
        COUNT(*)                                AS tx_count
    FROM dex_deployments
    GROUP BY symbol, chain, deployment_type, protocol
),

totals AS (
    SELECT SUM(total_usd) AS grand_total_usd FROM agg
)

SELECT
    a.symbol,
    a.chain,
    a.deployment_type,
    a.protocol,
    a.net_flow_usd,
    a.total_usd,
    ROUND(a.total_usd * 100.0 / NULLIF(t.grand_total_usd, 0), 2)           AS percentage_of_total,
    a.new_wallets,
    a.tx_count,
    '{{end_time}}'::TIMESTAMP_NTZ                                           AS time_bucket,
    'capital_deployment'                                                    AS category,
    ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN a.net_flow_usd >= 1000000          THEN 'HIGH_DEPLOYMENT_VOLUME'  ELSE NULL END,
        CASE WHEN a.new_wallets >= 10                THEN 'BROAD_ADOPTION'          ELSE NULL END,
        CASE WHEN a.net_flow_usd / NULLIF(a.new_wallets::FLOAT, 0) >= 100000
                                                     THEN 'WHALE_DEPLOYER'          ELSE NULL END,
        CASE WHEN a.tx_count >= 50                   THEN 'HIGH_ACTIVITY'           ELSE NULL END
    ))                                                                      AS signals,
    ARRAY_SIZE(ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN a.net_flow_usd >= 1000000          THEN 'HIGH_DEPLOYMENT_VOLUME'  ELSE NULL END,
        CASE WHEN a.new_wallets >= 10                THEN 'BROAD_ADOPTION'          ELSE NULL END,
        CASE WHEN a.net_flow_usd / NULLIF(a.new_wallets::FLOAT, 0) >= 100000
                                                     THEN 'WHALE_DEPLOYER'          ELSE NULL END,
        CASE WHEN a.tx_count >= 50                   THEN 'HIGH_ACTIVITY'           ELSE NULL END
    )))                                                                     AS signal_count
FROM agg a
CROSS JOIN totals t
ORDER BY net_flow_usd DESC
LIMIT 30
