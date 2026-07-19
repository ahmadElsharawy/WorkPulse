-- 002_add_employee_optional_fields.sql – add optional columns to employees table

ALTER TABLE employees
    ADD COLUMN IF NOT EXISTS residence_permit_end_date DATE,
    ADD COLUMN IF NOT EXISTS email VARCHAR(255),
    ADD COLUMN IF NOT EXISTS employee_number VARCHAR(50);
