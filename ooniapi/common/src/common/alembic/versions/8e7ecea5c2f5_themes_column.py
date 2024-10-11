"""themes column

Revision ID: 8e7ecea5c2f5
Revises: a037e908f3a0
Create Date: 2024-10-11 12:03:07.662702

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8e7ecea5c2f5"
down_revision: Union[str, None] = "a037e908f3a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def convert_json_to_array(column_name: str):
    op.add_column("oonifinding", sa.Column(f"{column_name}_tmp", sa.ARRAY(sa.String)))
    op.execute(
        f"""
        UPDATE oonifinding
        SET {column_name}_tmp = ARRAY(SELECT json_array_elements_text({column_name}))
    """
    )
    op.drop_column("oonifinding", column_name)
    op.alter_column("oonifinding", f"{column_name}_tmp", new_column_name=column_name)


def convert_array_to_json(column_name: str):
    op.add_column("oonifinding", sa.Column(f"{column_name}_tmp", sa.JSON()))
    op.execute(
        f"""
        UPDATE oonifinding
        SET {column_name}_tmp = to_json({column_name})
    """
    )
    op.drop_column("oonifinding", column_name)
    op.alter_column("oonifinding", f"{column_name}_tmp", new_column_name=column_name)


def upgrade() -> None:
    op.add_column("oonifinding", sa.Column("themes", sa.ARRAY(sa.String())))
    convert_json_to_array("country_codes")
    convert_json_to_array("asns")
    convert_json_to_array("domains")
    convert_json_to_array("tags")
    convert_json_to_array("links")
    convert_json_to_array("test_names")


def downgrade() -> None:
    op.drop_column("oonifinding", "themes")
    convert_array_to_json("country_codes")
    convert_array_to_json("asns")
    convert_array_to_json("domains")
    convert_array_to_json("tags")
    convert_array_to_json("links")
    convert_array_to_json("test_names")
