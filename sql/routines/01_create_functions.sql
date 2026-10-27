-- ==============================================================================
-- Database Functions
-- Stage 2: Database Performance, Index Optimization & Routines
-- Author: Shayan Ganji
-- ==============================================================================

-- 1. Scalar Function: Delivery Delay Calculation
-- Computes fractional delay in days between actual delivery date and estimated promise date.
-- Usable directly inside SELECT projections, WHERE filters, or GROUP BY clauses.
CREATE OR REPLACE FUNCTION olist.fn_calculate_delivery_delay_days(
    p_delivered TIMESTAMPTZ,
    p_estimated TIMESTAMPTZ
)
RETURNS NUMERIC
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    IF p_delivered IS NULL OR p_estimated IS NULL THEN
        RETURN NULL;
    END IF;
    RETURN ROUND((EXTRACT(EPOCH FROM (p_delivered - p_estimated)) / 86400.0)::numeric, 2);
END;
$$;


-- 2. Scalar Function: Net Promoter Score (NPS) Sentiment Classification
-- Maps integer review scores (1-5) to canonical customer sentiment tiers:
-- Scores 4-5: 'Promoter' | Score 3: 'Passive' | Scores 1-2: 'Detractor'
CREATE OR REPLACE FUNCTION olist.fn_customer_nps_tier(p_score INT)
RETURNS VARCHAR(20)
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    IF p_score IS NULL THEN
        RETURN 'Unknown';
    ELSIF p_score >= 4 THEN
        RETURN 'Promoter';
    ELSIF p_score = 3 THEN
        RETURN 'Passive';
    ELSIF p_score BETWEEN 1 AND 2 THEN
        RETURN 'Detractor';
    ELSE
        RETURN 'Invalid';
    END IF;
END;
$$;
