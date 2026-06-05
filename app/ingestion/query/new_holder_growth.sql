-- New Holder Growth: Tracks organic adoption by counting first-time token acquirers.
-- Compares current window to prior window of equal length.
-- Parameters: {{token_address}}, {{time_window_hours}}, {{end_time}}

WITH token_meta AS (
    SELECT symbol
    FROM tokens.erc20
    WHERE blockchain = 'ethereum'
      AND contract_address = {{token_address}}
    LIMIT 1
),

first_acquisition AS (
    SELECT
        "to"                  AS wallet,
        MIN(evt_block_time)   AS first_received
    FROM erc20_ethereum.evt_Transfer
    WHERE contract_address = {{token_address}}
      AND "to" != 0x0000000000000000000000000000000000000000
    GROUP BY "to"
),

new_holders_current AS (
    SELECT COUNT(*) AS new_wallets
    FROM first_acquisition
    WHERE first_received >= TIMESTAMP '{{end_time}}' - INTERVAL '{{time_window_hours}}' HOUR
      AND first_received <  TIMESTAMP '{{end_time}}'
),

new_holders_prior AS (
    SELECT COUNT(*) AS prior_new_wallets
    FROM first_acquisition
    WHERE first_received >= TIMESTAMP '{{end_time}}' - 2 * INTERVAL '{{time_window_hours}}' HOUR
      AND first_received <  TIMESTAMP '{{end_time}}' - INTERVAL '{{time_window_hours}}' HOUR
),

total_holders AS (
    SELECT COUNT(DISTINCT "to") AS total
    FROM erc20_ethereum.evt_Transfer
    WHERE contract_address = {{token_address}}
      AND "to" != 0x0000000000000000000000000000000000000000
),

active_in_window AS (
    SELECT COUNT(DISTINCT addr) AS active_addresses
    FROM (
        SELECT "to"   AS addr FROM erc20_ethereum.evt_Transfer
        WHERE contract_address = {{token_address}}
          AND evt_block_time >= TIMESTAMP '{{end_time}}' - INTERVAL '{{time_window_hours}}' HOUR
          AND evt_block_time <  TIMESTAMP '{{end_time}}'
          AND "to" != 0x0000000000000000000000000000000000000000
        UNION
        SELECT "from" AS addr FROM erc20_ethereum.evt_Transfer
        WHERE contract_address = {{token_address}}
          AND evt_block_time >= TIMESTAMP '{{end_time}}' - INTERVAL '{{time_window_hours}}' HOUR
          AND evt_block_time <  TIMESTAMP '{{end_time}}'
          AND "from" != 0x0000000000000000000000000000000000000000
    ) addrs
),

preoutput AS (
    SELECT
        tm.symbol,
        nhc.new_wallets,
        nhp.prior_new_wallets,
        ROUND(
            (nhc.new_wallets - nhp.prior_new_wallets) * 100.0
            / NULLIF(nhp.prior_new_wallets, 0), 2
        )                                                               AS holder_growth_pct,
        th.total                                                        AS total_holders_all_time,
        ROUND(nhc.new_wallets * 100.0 / NULLIF(th.total, 0), 4)        AS first_time_users_pct,
        aw.active_addresses,
        NOW() - INTERVAL '{{time_window_hours}}' HOUR                  AS window_start_time,
        NOW()                                                           AS window_end_time,
        date_trunc('hour', NOW())                                       AS time_bucket,
        'organic_adoption'                                              AS category,
        FILTER(
            ARRAY[
                CASE WHEN (nhc.new_wallets - nhp.prior_new_wallets) * 100.0
                          / NULLIF(nhp.prior_new_wallets, 0) > 50
                     THEN 'EXPLOSIVE_GROWTH' END,
                CASE WHEN (nhc.new_wallets - nhp.prior_new_wallets) * 100.0
                          / NULLIF(nhp.prior_new_wallets, 0) BETWEEN 20 AND 50
                     THEN 'STRONG_GROWTH' END,
                CASE WHEN (nhc.new_wallets - nhp.prior_new_wallets) * 100.0
                          / NULLIF(nhp.prior_new_wallets, 0) BETWEEN 0 AND 20
                     THEN 'STEADY_GROWTH' END,
                CASE WHEN (nhc.new_wallets - nhp.prior_new_wallets) * 100.0
                          / NULLIF(nhp.prior_new_wallets, 0) < 0
                     THEN 'DECLINING_ADOPTION' END,
                CASE WHEN nhc.new_wallets * 100.0 / NULLIF(th.total, 0) > 1
                     THEN 'HIGH_NEW_USER_RATIO' END
            ],
            x -> x IS NOT NULL
        )                                                               AS signals
    FROM new_holders_current nhc
    CROSS JOIN new_holders_prior nhp
    CROSS JOIN total_holders th
    CROSS JOIN active_in_window aw
    CROSS JOIN token_meta tm
)

SELECT
    symbol,
    new_wallets,
    prior_new_wallets,
    holder_growth_pct,
    total_holders_all_time,
    first_time_users_pct,
    active_addresses,
    window_start_time,
    window_end_time,
    time_bucket,
    category,
    signals,
    CARDINALITY(signals) AS signal_count
FROM preoutput
