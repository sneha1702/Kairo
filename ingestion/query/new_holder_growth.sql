-- Narrative Context: New Holder Growth Rate
-- Tracks the rate of new unique wallets acquiring a token over time
-- Parameters: {{token_address}}, {{time_window_hours}} (e.g. 1, 6, 24)

WITH first_acquisition AS (
    -- Find when each wallet first received the token
    SELECT
        "to"                                            AS wallet,
        MIN(evt_block_time)                             AS first_received
    FROM erc20_ethereum.evt_Transfer
    WHERE contract_address = {{token_address}}
      AND "to" != 0x0000000000000000000000000000000000000000
    GROUP BY "to"
),

new_holders_current AS (
    SELECT
        COUNT(*)                AS new_holders
    FROM first_acquisition
    WHERE first_received >= NOW() - INTERVAL '{{time_window_hours}}' HOUR
),

new_holders_prior AS (
    -- Same window size, one period back (for growth rate)
    SELECT
        COUNT(*)                AS prior_new_holders
    FROM first_acquisition
    WHERE first_received >= NOW() - INTERVAL '{{time_window_hours}}' HOUR * 2
      AND first_received  <  NOW() - INTERVAL '{{time_window_hours}}' HOUR
),

total_holders AS (
    SELECT COUNT(DISTINCT "to") AS total
    FROM erc20_ethereum.evt_Transfer
    WHERE contract_address = {{token_address}}
      AND "to" != 0x0000000000000000000000000000000000000000
),

hourly_breakdown AS (
    SELECT
        date_trunc('hour', first_received)  AS hour,
        COUNT(*)                            AS new_holders_per_hour
    FROM first_acquisition
    WHERE first_received >= NOW() - INTERVAL '{{time_window_hours}}' HOUR
    GROUP BY 1
    ORDER BY 1
)

SELECT
    'Summary'                                           AS view_type,
    nhc.new_holders                                     AS new_holders_current_window,
    nhp.prior_new_holders                               AS new_holders_prior_window,
    ROUND(
        (nhc.new_holders - nhp.prior_new_holders) * 100.0
        / NULLIF(nhp.prior_new_holders, 0), 2
    )                                                   AS growth_rate_pct,
    th.total                                            AS total_holders_all_time,
    ROUND(nhc.new_holders * 100.0 / NULLIF(th.total, 0), 4) AS new_holders_pct_of_total,
    CASE
        WHEN (nhc.new_holders - nhp.prior_new_holders) * 100.0
             / NULLIF(nhp.prior_new_holders, 0) > 50
            THEN '🚀 Explosive Growth'
        WHEN (nhc.new_holders - nhp.prior_new_holders) * 100.0
             / NULLIF(nhp.prior_new_holders, 0) > 20
            THEN '📈 Strong Growth'
        WHEN (nhc.new_holders - nhp.prior_new_holders) * 100.0
             / NULLIF(nhp.prior_new_holders, 0) > 0
            THEN '✅ Steady Growth'
        ELSE '📉 Declining Adoption'
    END                                                 AS growth_signal
FROM new_holders_current nhc
CROSS JOIN new_holders_prior nhp
CROSS JOIN total_holders th

UNION ALL

SELECT
    'Hourly Breakdown'                                  AS view_type,
    hb.new_holders_per_hour                             AS new_holders_current_window,
    NULL                                                AS new_holders_prior_window,
    NULL                                                AS growth_rate_pct,
    NULL                                                AS total_holders_all_time,
    NULL                                                AS new_holders_pct_of_total,
    CAST(hb.hour AS VARCHAR)                            AS growth_signal
FROM hourly_breakdown hb
