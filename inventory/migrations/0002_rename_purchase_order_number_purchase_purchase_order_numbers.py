from django.db import migrations

def conditional_rename(apps, schema_editor):
    # Adjust table_name, old_column, new_column if your table/columns differ.
    table_name = 'inventory_purchase'
    old_column = 'purchase_order_number'
    new_column = 'purchase_purchase_order_numbers'

    sql = f"""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = '{table_name}' AND column_name = '{old_column}'
      ) THEN
        ALTER TABLE {table_name} RENAME COLUMN {old_column} TO {new_column};
      END IF;
    END
    $$;
    """
    schema_editor.execute(sql)

class Migration(migrations.Migration):

    dependencies = [
        # Replace with the actual previous migration dependency for inventory,
        # e.g. ('inventory', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(conditional_rename),
    ]