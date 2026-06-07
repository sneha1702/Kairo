-- New Holder Growth: Count of first-ever receivers of {{token_address}} in window.
-- Parameters: {{token_address}}, {{time_window_hours}}, {{end_time}}

WITH first_receipts AS (
    SELECT
        to_address                              AS address,
        MIN(block_timestamp)                    AS first_received_at
    FROM ethereum.core.ez_token_transfers
    WHERE LOWER(contract_address) = LOWER('{{token_address}}')
      AND to_address != '0x0000000000000000000000000000000000000000'
    GROUP BY to_address
),

new_in_window AS (
    SELECT COUNT(*) AS new_holder_count
    FROM first_receipts
    WHERE first_received_at >= TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
      AND first_received_at <  '{{end_time}}'::TIMESTAMP_NTZ
),

prior_in_window AS (
    SELECT COUNT(*) AS prior_holder_count
    FROM first_receipts
    WHERE first_received_at >= TIMESTAMPADD(HOUR, -2 * {{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
      AND first_received_at <  TIMESTAMPADD(HOUR, -{{time_window_hours}}, '{{end_time}}'::TIMESTAMP_NTZ)
),

token_info AS (
    SELECT symbol
    FROM ethereum.core.dim_contracts
    WHERE LOWER(address) = LOWER('{{token_address}}')
    LIMIT 1
)

SELECT
    ti.symbol,
    nw.new_holder_count,
    pw.prior_holder_count,
    ROUND(
        (nw.new_holder_count - pw.prior_holder_count) * 100.0
        / NULLIF(pw.prior_holder_count, 0), 2
    )                                                                           AS growth_pct,
    '{{end_time}}'::TIMESTAMP_NTZ                                               AS time_bucket,
    'holder_growth'                                                             AS category,
    ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN nw.new_holder_count > pw.prior_holder_count * 1.5  THEN 'RAPID_HOLDER_GROWTH'  ELSE NULL END,
        CASE WHEN nw.new_holder_count > pw.prior_holder_count        THEN 'STEADY_HOLDER_GROWTH' ELSE NULL END,
        CASE WHEN nw.new_holder_count >= 1000                        THEN 'HIGH_ADOPTION_VOLUME' ELSE NULL END,
        CASE WHEN nw.new_holder_count < pw.prior_holder_count        THEN 'SLOWING_GROWTH'       ELSE NULL END
    ))                                                                          AS signals,
    ARRAY_SIZE(ARRAY_COMPACT(ARRAY_CONSTRUCT(
        CASE WHEN nw.new_holder_count > pw.prior_holder_count * 1.5  THEN 'RAPID_HOLDER_GROWTH'  ELSE NULL END,
        CASE WHEN nw.new_holder_count > pw.prior_holder_count        THEN 'STEADY_HOLDER_GROWTH' ELSE NULL END,
        CASE WHEN nw.new_holder_count >= 1000                        THEN 'HIGH_ADOPTION_VOLUME' ELSE NULL END,
        CASE WHEN nw.new_holder_count < pw.prior_holder_count        THEN 'SLOWING_GROWTH'       ELSE NULL END
    )))                                                                         AS signal_count
FROM new_in_window nw
CROSS JOIN prior_in_window pw
CROSS JOIN token_info ti
