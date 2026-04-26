"""Initial schema for art style classifier backend."""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "styles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_styles_code", "styles", ["code"], unique=True)

    op.create_table(
        "inference_tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("s3_key", sa.String(length=512), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_inference_tasks_status", "inference_tasks", ["status"], unique=False)
    op.create_unique_constraint("uq_inference_tasks_s3_key", "inference_tasks", ["s3_key"])

    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("inference_tasks.id"), nullable=False),
        sa.Column("top_style_id", sa.Integer(), sa.ForeignKey("styles.id"), nullable=False),
        sa.Column("top_confidence", sa.Float(), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("model_version", sa.String(length=255), nullable=False),
        sa.Column("model_source", sa.String(length=64), nullable=False),
        sa.Column("raw_response", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_predictions_task_id", "predictions", ["task_id"])
    op.create_index("ix_predictions_task_id", "predictions", ["task_id"], unique=False)

    op.create_table(
        "prediction_candidates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("prediction_id", sa.Integer(), sa.ForeignKey("predictions.id"), nullable=False),
        sa.Column("style_id", sa.Integer(), sa.ForeignKey("styles.id"), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
    )
    op.create_index("ix_prediction_candidates_prediction_id", "prediction_candidates", ["prediction_id"], unique=False)

    op.create_table(
        "model_registry_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("model_version", sa.String(length=255), nullable=False),
        sa.Column("model_source", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "retrain_exports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("export_key", sa.String(length=512), nullable=False),
        sa.Column("records_count", sa.Integer(), nullable=False),
        sa.Column("payload_preview", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_retrain_exports_export_key", "retrain_exports", ["export_key"])

    op.create_table(
        "admin_actions_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("admin_actions_log")
    op.drop_constraint("uq_retrain_exports_export_key", "retrain_exports", type_="unique")
    op.drop_table("retrain_exports")
    op.drop_table("model_registry_state")
    op.drop_index("ix_prediction_candidates_prediction_id", table_name="prediction_candidates")
    op.drop_table("prediction_candidates")
    op.drop_index("ix_predictions_task_id", table_name="predictions")
    op.drop_constraint("uq_predictions_task_id", "predictions", type_="unique")
    op.drop_table("predictions")
    op.drop_constraint("uq_inference_tasks_s3_key", "inference_tasks", type_="unique")
    op.drop_index("ix_inference_tasks_status", table_name="inference_tasks")
    op.drop_table("inference_tasks")
    op.drop_index("ix_styles_code", table_name="styles")
    op.drop_table("styles")

