"""Database-level guarantee that ledger history can never be edited or deleted (Postgres only).

The model layer already refuses these operations; the trigger also covers cascade deletes, raw SQL and
future bugs. TRUNCATE and superuser DDL are outside its scope — restrict those via database roles.
"""
from django.db import migrations

CREATE = """
CREATE OR REPLACE FUNCTION ledger_forbid_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'ledger rows are append-only';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER ledger_entry_append_only BEFORE UPDATE OR DELETE ON ledger_entry
    FOR EACH ROW EXECUTE FUNCTION ledger_forbid_mutation();
CREATE TRIGGER ledger_transaction_append_only BEFORE UPDATE OR DELETE ON ledger_ledgertransaction
    FOR EACH ROW EXECUTE FUNCTION ledger_forbid_mutation();
"""

DROP = """
DROP TRIGGER IF EXISTS ledger_transaction_append_only ON ledger_ledgertransaction;
DROP TRIGGER IF EXISTS ledger_entry_append_only ON ledger_entry;
DROP FUNCTION IF EXISTS ledger_forbid_mutation();
"""


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(CREATE)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(DROP)


class Migration(migrations.Migration):
    dependencies = [("ledger", "0001_initial")]
    operations = [migrations.RunPython(forwards, backwards)]
