-- Post-Bridge Deployment: bridge recipients deploying capital to DEX on destination chains.
-- Each row = one (symbol, chain, protocol) group for the current time window.
-- Parameters: {{time_window_hours}}, {{min_usd_value}}, {{end_time}}

WITH bridge_recipients AS (
    SELECT
        LOWER(withdrawal_chain) AS dest_chain,
        recipient,
        SUM(deposit_amount_usd) AS bridged_usd
    FROM bridges_evms.deposits
    WHERE block_time >= TIMESTAMP '{{end_time}}' - INTERVAL '{{time_window_hours}}' HOUR
      AND block_time <  TIMESTAMP '{{end_time}}'
      AND deposit_amount_usd >= {{min_usd_value}}
      AND recipient IS NOT NULL
    GROUP BY LOWER(withdrawal_chain), recipient
),

dex_deployments AS (
    SELECT
        t.blockchain AS chain,
        t.taker AS deployer,
        COALESCE(t.token_bought_symbol, 'UNKNOWN') AS symbol,
        t.amount_usd AS deployed_usd,
        COALESCE(t.project, 'unknown_dex') AS protocol,
        'dex' AS deployment_type
    FROM dex.trades t
    INNER JOIN bridge_recipients br
        ON t.taker = br.recipient
        AND t.blockchain = br.dest_chain
    WHERE t.block_time >= TIMESTAMP '{{end_time}}' - INTERVAL '{{time_window_hours}}' HOUR
      AND t.block_time <  TIMESTAMP '{{end_time}}'
      AND t.amount_usd >= 1000
      AND t.amount_usd IS NOT NULL
),

agg AS (
    SELECT
        symbol,
        chain,
        deployment_type,
        protocol,
        ROUND(SUM(deployed_usd), 2) AS net_flow_usd,
        ROUND(SUM(deployed_usd), 2) AS total_usd,
        COUNT(DISTINCT deployer) AS new_wallets,
        COUNT(*) AS tx_count
    FROM dex_deployments
    GROUP BY symbol, chain, deployment_type, protocol
),

totals AS (
    SELECT SUM(total_usd) AS grand_total_usd FROM agg
),

preoutput AS (
    SELECT
        a.symbol,
        a.chain,
        a.deployment_type,
        a.protocol,
        a.net_flow_usd,
        a.total_usd,
        ROUND(a.total_usd * 100.0 / NULLIF(t.grand_total_usd, 0), 2) AS percentage_of_total,
        a.new_wallets,
        a.tx_count,
        TIMESTAMP '{{end_time}}' AS time_bucket,
        'capital_deployment' AS category,
        FILTER(
            ARRAY[
                CASE WHEN a.net_flow_usd >= 1000000 THEN 'HIGH_DEPLOYMENT_VOLUME' END,
                CASE WHEN a.new_wallets >= 10 THEN 'BROAD_ADOPTION' END,
                CASE WHEN a.net_flow_usd / NULLIF(CAST(a.new_wallets AS DOUBLE), 0) >= 100000 THEN 'WHALE_DEPLOYER' END,
                CASE WHEN a.tx_count >= 50 THEN 'HIGH_ACTIVITY' END
            ],
            x -> x IS NOT NULL
        ) AS signals
    FROM agg a
    CROSS JOIN totals t
)

SELECT
    symbol,
    chain,
    deployment_type,
    protocol,
    net_flow_usd,
    total_usd,
    percentage_of_total,
    new_wallets,
    tx_count,
    time_bucket,
    category,
    signals,
    CARDINALITY(signals) AS signal_count
FROM preoutput
ORDER BY net_flow_usd DESC
LIMIT 30
