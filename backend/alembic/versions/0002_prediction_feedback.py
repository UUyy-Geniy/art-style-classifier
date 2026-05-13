"""Add prediction feedback for retraining."""

from alembic import op
import sqlalchemy as sa


revision = "0002_prediction_feedback"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_feedback",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("inference_tasks.id"), nullable=False),
        sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("correct_style_id", sa.Integer(), sa.ForeignKey("styles.id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("used_in_training", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("used_in_training_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_prediction_feedback_status", "prediction_feedback", ["status"], unique=False)
    op.create_index("ix_prediction_feedback_used_in_training", "prediction_feedback", ["used_in_training"], unique=False)
    op.create_unique_constraint("uq_prediction_feedback_task_id", "prediction_feedback", ["task_id"])


def downgrade() -> None:
    op.drop_constraint("uq_prediction_feedback_task_id", "prediction_feedback", type_="unique")
    op.drop_index("ix_prediction_feedback_used_in_training", table_name="prediction_feedback")
    op.drop_index("ix_prediction_feedback_status", table_name="prediction_feedback")
    op.drop_table("prediction_feedback")
