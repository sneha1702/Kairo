-- Protocol Inflow Leaderboard: USD deposits into Aave v3, EigenLayer, and Lido.
-- symbol = protocol name. Each row = one (protocol, deployment_type) per window.
-- volume_multiplier compares current vs prior period of the same length.
-- Parameters: {{time_window_hours}}, {{min_usd_value}}, {{end_time}}

WITH aave_raw AS (
    SELECT
        s.evt_block_time AS block_time,
        s.onBehalfOf AS depositor,
        CAST(s.amount AS DOUBLE) / POW(10, COALESCE(tk.decimals, 18)) * COALESCE(p.price, 0) AS usd_value,
        'Aave_v3' AS protocol,
        'lending' AS deployment_type
    FROM aave_v3_ethereum.Pool_evt_Supply s
    LEFT JOIN tokens.erc20 tk
        ON tk.blockchain = 'ethereum'
        AND tk.contract_address = s.reserve
    LEFT JOIN prices.usd p
        ON p.blockchain = 'ethereum'
        AND p.contract_address = s.reserve
        AND p.minute = date_trunc('minute', s.evt_block_time)
    WHERE s.evt_block_time >= TIMESTAMP '{{end_time}}' - 2 * INTERVAL '{{time_window_hours}}' HOUR
      AND s.evt_block_time <  TIMESTAMP '{{end_time}}'
),

eigenlayer_raw AS (
    SELECT
        d.evt_block_time AS block_time,
        d.depositor,
        CAST(d.shares AS DOUBLE) / 1e18 * COALESCE(p.price, 0) AS usd_value,
        'EigenLayer' AS protocol,
        'restaking' AS deployment_type
    FROM eigenlayer_ethereum.StrategyManager_evt_Deposit d
    LEFT JOIN prices.usd p
        ON p.blockchain = 'ethereum'
        AND p.contract_address = d.token
        AND p.minute = date_trunc('minute', d.evt_block_time)
    WHERE d.evt_block_time >= NOW() - 2 * INTERVAL '{{time_window_hours}}' HOUR
),

lido_raw AS (
    SELECT
        s.evt_block_time AS block_time,
        s.sender AS depositor,
        -- ETH submitted to Lido: priced via WETH as ETH proxy
        CAST(s.amount AS DOUBLE) / 1e18 * COALESCE(p.price, 0) AS usd_value,
        'Lido' AS protocol,
        'liquid_staking' AS deployment_type
    FROM lido_ethereum.steth_evt_Submitted s
    LEFT JOIN prices.usd p
        ON p.blockchain = 'ethereum'
        AND p.contract_address = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2
        AND p.minute = date_trunc('minute', s.evt_block_time)
    WHERE s.evt_block_time >= NOW() - 2 * INTERVAL '{{time_window_hours}}' HOUR
),

all_raw AS (
    SELECT block_time, depositor, usd_value, protocol, deployment_type FROM aave_raw
    UNION ALL
    SELECT block_time, depositor, usd_value, protocol, deployment_type FROM eigenlayer_raw
    UNION ALL
    SELECT block_time, depositor, usd_value, protocol, deployment_type FROM lido_raw
),

agg AS (
    SELECT
        protocol AS symbol,
        deployment_type,
        ROUND(SUM(CASE WHEN block_time >= NOW() - INTERVAL '{{time_window_hours}}' HOUR
                       THEN usd_value ELSE 0 END), 2) AS net_flow_usd,
        ROUND(SUM(CASE WHEN block_time >= NOW() - INTERVAL '{{time_window_hours}}' HOUR
                       THEN usd_value ELSE 0 END), 2) AS total_usd,
        ROUND(SUM(CASE WHEN block_time >= NOW() - INTERVAL '{{time_window_hours}}' HOUR
                            AND usd_value >= {{min_usd_value}}
                       THEN usd_value ELSE 0 END), 2) AS whale_usd,
        COUNT(DISTINCT CASE WHEN block_time >= NOW() - INTERVAL '{{time_window_hours}}' HOUR
                            THEN depositor END) AS new_wallets,
        ROUND(SUM(CASE WHEN block_time < NOW() - INTERVAL '{{time_window_hours}}' HOUR
                       THEN usd_value ELSE 0 END), 2) AS prior_usd
    FROM all_raw
    WHERE usd_value > 0
    GROUP BY protocol, deployment_type
),

preoutput AS (
    SELECT
        a.symbol,
        a.deployment_type,
        a.net_flow_usd,
        a.total_usd,
        a.whale_usd,
        a.new_wallets,
        ROUND(a.net_flow_usd / NULLIF(a.prior_usd, 0), 2) AS volume_multiplier,
        date_trunc('hour', NOW()) AS time_bucket,
        'protocol_inflow' AS category,
        FILTER(
            ARRAY[
                CASE WHEN a.net_flow_usd >= 10000000 THEN 'HIGH_PROTOCOL_INFLOW' END,
                CASE WHEN a.whale_usd / NULLIF(a.net_flow_usd, 0) >= 0.5
                     THEN 'WHALE_DOMINATED' END,
                CASE WHEN a.new_wallets >= 100 THEN 'BROAD_ADOPTION' END,
                CASE WHEN a.net_flow_usd / NULLIF(a.prior_usd, 0) >= 2.0
                     THEN 'ACCELERATING_INFLOW' END
            ],
            x -> x IS NOT NULL
        ) AS signals
    FROM agg a
)

SELECT
    symbol,
    deployment_type,
    net_flow_usd,
    total_usd,
    whale_usd,
    new_wallets,
    volume_multiplier,
    time_bucket,
    category,
    signals,
    CARDINALITY(signals) AS signal_count
FROM preoutput
ORDER BY net_flow_usd DESC
