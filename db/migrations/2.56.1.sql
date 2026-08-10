-- Re-auditoría v2.56.0 (hallazgo crítico): billingblock=0 hace que
-- rating.py::billable_blocks() dispare ZeroDivisionError. Los modelos
-- Pydantic ya validan Field(ge=1) en el alta desde el panel/API — este CHECK
-- es la defensa en profundidad a nivel de columna, para cualquier INSERT/UPDATE
-- que no pase por esos modelos (scripts, corrección manual en producción).
-- Probado contra MariaDB 11.8.6 real: ADD CONSTRAINT IF NOT EXISTS + CHECK
-- rechaza billingblock=0 y es idempotente en una segunda corrida.
ALTER TABLE rates ADD CONSTRAINT IF NOT EXISTS chk_rates_billingblock CHECK (billingblock >= 1);
ALTER TABLE carrier_rates ADD CONSTRAINT IF NOT EXISTS chk_carrier_rates_billingblock CHECK (billingblock >= 1);
ALTER TABLE rate_plan_draft_items ADD CONSTRAINT IF NOT EXISTS chk_draft_items_billingblock CHECK (billingblock >= 1);
