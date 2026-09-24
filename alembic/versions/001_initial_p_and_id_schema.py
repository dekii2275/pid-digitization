"""Initial P&ID schema migration (Milestone M1).

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-20 07:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. projects
    op.create_table(
        'projects',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_projects_id'), 'projects', ['id'], unique=False)
    op.create_index(op.f('ix_projects_name'), 'projects', ['name'], unique=False)

    # 2. drawings
    op.create_table(
        'drawings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=1024), nullable=False),
        sa.Column('file_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('page_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_drawings_id'), 'drawings', ['id'], unique=False)
    op.create_index(op.f('ix_drawings_name'), 'drawings', ['name'], unique=False)
    op.create_index(op.f('ix_drawings_project_id'), 'drawings', ['project_id'], unique=False)
    op.create_index(op.f('ix_drawings_status'), 'drawings', ['status'], unique=False)

    # 3. drawing_pages
    op.create_table(
        'drawing_pages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('drawing_id', sa.Integer(), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=False),
        sa.Column('width', sa.Integer(), nullable=False),
        sa.Column('height', sa.Integer(), nullable=False),
        sa.Column('image_path', sa.String(length=1024), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['drawing_id'], ['drawings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_drawing_pages_drawing_id'), 'drawing_pages', ['drawing_id'], unique=False)
    op.create_index(op.f('ix_drawing_pages_id'), 'drawing_pages', ['id'], unique=False)

    # 4. processing_jobs
    op.create_table(
        'processing_jobs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.String(length=64), nullable=False),
        sa.Column('drawing_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('current_stage', sa.String(length=50), nullable=False),
        sa.Column('progress', sa.Integer(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('stage_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['drawing_id'], ['drawings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_processing_jobs_drawing_id'), 'processing_jobs', ['drawing_id'], unique=False)
    op.create_index(op.f('ix_processing_jobs_id'), 'processing_jobs', ['id'], unique=False)
    op.create_index(op.f('ix_processing_jobs_job_id'), 'processing_jobs', ['job_id'], unique=True)
    op.create_index(op.f('ix_processing_jobs_status'), 'processing_jobs', ['status'], unique=False)

    # 5. symbols
    op.create_table(
        'symbols',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('drawing_id', sa.Integer(), nullable=False),
        sa.Column('page_id', sa.Integer(), nullable=True),
        sa.Column('class_name', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('bbox_x1', sa.Float(), nullable=False),
        sa.Column('bbox_y1', sa.Float(), nullable=False),
        sa.Column('bbox_x2', sa.Float(), nullable=False),
        sa.Column('bbox_y2', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('tag', sa.String(length=100), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('model_version', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['drawing_id'], ['drawings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['page_id'], ['drawing_pages.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_symbols_category'), 'symbols', ['category'], unique=False)
    op.create_index(op.f('ix_symbols_class_name'), 'symbols', ['class_name'], unique=False)
    op.create_index(op.f('ix_symbols_drawing_id'), 'symbols', ['drawing_id'], unique=False)
    op.create_index(op.f('ix_symbols_id'), 'symbols', ['id'], unique=False)
    op.create_index(op.f('ix_symbols_page_id'), 'symbols', ['page_id'], unique=False)
    op.create_index(op.f('ix_symbols_tag'), 'symbols', ['tag'], unique=False)

    # 6. ocr_texts
    op.create_table(
        'ocr_texts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('drawing_id', sa.Integer(), nullable=False),
        sa.Column('page_id', sa.Integer(), nullable=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('bbox_x1', sa.Float(), nullable=False),
        sa.Column('bbox_y1', sa.Float(), nullable=False),
        sa.Column('bbox_x2', sa.Float(), nullable=False),
        sa.Column('bbox_y2', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('ocr_engine', sa.String(length=50), nullable=False),
        sa.Column('associated_symbol_id', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['associated_symbol_id'], ['symbols.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['drawing_id'], ['drawings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['page_id'], ['drawing_pages.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ocr_texts_associated_symbol_id'), 'ocr_texts', ['associated_symbol_id'], unique=False)
    op.create_index(op.f('ix_ocr_texts_drawing_id'), 'ocr_texts', ['drawing_id'], unique=False)
    op.create_index(op.f('ix_ocr_texts_id'), 'ocr_texts', ['id'], unique=False)
    op.create_index(op.f('ix_ocr_texts_page_id'), 'ocr_texts', ['page_id'], unique=False)
    op.create_index(op.f('ix_ocr_texts_text'), 'ocr_texts', ['text'], unique=False)

    # 7. lines
    op.create_table(
        'lines',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('drawing_id', sa.Integer(), nullable=False),
        sa.Column('page_id', sa.Integer(), nullable=True),
        sa.Column('line_type', sa.String(length=50), nullable=False),
        sa.Column('geometry', sa.JSON(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('flow_direction', sa.String(length=50), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['drawing_id'], ['drawings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['page_id'], ['drawing_pages.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_lines_drawing_id'), 'lines', ['drawing_id'], unique=False)
    op.create_index(op.f('ix_lines_id'), 'lines', ['id'], unique=False)
    op.create_index(op.f('ix_lines_line_type'), 'lines', ['line_type'], unique=False)
    op.create_index(op.f('ix_lines_page_id'), 'lines', ['page_id'], unique=False)

    # 8. relationships
    op.create_table(
        'relationships',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('drawing_id', sa.Integer(), nullable=False),
        sa.Column('from_symbol_id', sa.Integer(), nullable=False),
        sa.Column('to_symbol_id', sa.Integer(), nullable=False),
        sa.Column('relation_type', sa.String(length=50), nullable=False),
        sa.Column('line_id', sa.Integer(), nullable=True),
        sa.Column('line_tag', sa.String(length=100), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['drawing_id'], ['drawings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['from_symbol_id'], ['symbols.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['line_id'], ['lines.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['to_symbol_id'], ['symbols.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_relationships_drawing_id'), 'relationships', ['drawing_id'], unique=False)
    op.create_index(op.f('ix_relationships_from_symbol_id'), 'relationships', ['from_symbol_id'], unique=False)
    op.create_index(op.f('ix_relationships_id'), 'relationships', ['id'], unique=False)
    op.create_index(op.f('ix_relationships_line_id'), 'relationships', ['line_id'], unique=False)
    op.create_index(op.f('ix_relationships_relation_type'), 'relationships', ['relation_type'], unique=False)
    op.create_index(op.f('ix_relationships_to_symbol_id'), 'relationships', ['to_symbol_id'], unique=False)

    # 9. revisions
    op.create_table(
        'revisions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('drawing_id', sa.Integer(), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('before_state', sa.JSON(), nullable=True),
        sa.Column('after_state', sa.JSON(), nullable=True),
        sa.Column('user_identifier', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['drawing_id'], ['drawings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_revisions_drawing_id'), 'revisions', ['drawing_id'], unique=False)
    op.create_index(op.f('ix_revisions_entity_id'), 'revisions', ['entity_id'], unique=False)
    op.create_index(op.f('ix_revisions_entity_type'), 'revisions', ['entity_type'], unique=False)
    op.create_index(op.f('ix_revisions_id'), 'revisions', ['id'], unique=False)

    # 10. audit_logs
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('drawing_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['drawing_id'], ['drawings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_drawing_id'), 'audit_logs', ['drawing_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_id'), 'audit_logs', ['id'], unique=False)

    # 11. exports
    op.create_table(
        'exports',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('drawing_id', sa.Integer(), nullable=False),
        sa.Column('export_type', sa.String(length=50), nullable=False),
        sa.Column('file_path', sa.String(length=1024), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['drawing_id'], ['drawings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_exports_drawing_id'), 'exports', ['drawing_id'], unique=False)
    op.create_index(op.f('ix_exports_export_type'), 'exports', ['export_type'], unique=False)
    op.create_index(op.f('ix_exports_id'), 'exports', ['id'], unique=False)


def downgrade() -> None:
    op.drop_table('exports')
    op.drop_table('audit_logs')
    op.drop_table('revisions')
    op.drop_table('relationships')
    op.drop_table('lines')
    op.drop_table('ocr_texts')
    op.drop_table('symbols')
    op.drop_table('processing_jobs')
    op.drop_table('drawing_pages')
    op.drop_table('drawings')
    op.drop_table('projects')
