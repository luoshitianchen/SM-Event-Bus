"""新增业务表（事件主题 / 订阅 / 消息）

Revision ID: 0002_business_tables
Revises: 0001_initial
Create Date: 2026-09-23
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# 本迁移由 autogenerate 生成，手动调整 revision 标识为 0002_business_tables
revision: str = '0002_business_tables'
down_revision: Union[str, None] = '0001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### 自动生成开始：创建事件总线业务表 ###
    # 事件消息表：存储待投递 / 已投递的事件消息
    op.create_table('event_messages',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('topic_id', sa.String(length=64), nullable=False),
    sa.Column('payload', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('retry_count', sa.Integer(), nullable=False),
    sa.Column('max_retries', sa.Integer(), nullable=False),
    sa.Column('last_error', sa.Text(), nullable=False),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_event_messages_status'), 'event_messages', ['status'], unique=False)
    op.create_index(op.f('ix_event_messages_topic_id'), 'event_messages', ['topic_id'], unique=False)
    # 事件订阅表：订阅方对 topic 的回调地址与状态
    op.create_table('event_subscriptions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('topic_id', sa.String(length=64), nullable=False),
    sa.Column('subscriber_name', sa.String(length=128), nullable=False),
    sa.Column('endpoint_url', sa.String(length=512), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_event_subscriptions_status'), 'event_subscriptions', ['status'], unique=False)
    op.create_index(op.f('ix_event_subscriptions_subscriber_name'), 'event_subscriptions', ['subscriber_name'], unique=False)
    op.create_index(op.f('ix_event_subscriptions_topic_id'), 'event_subscriptions', ['topic_id'], unique=False)
    # 事件主题表：topic 定义与状态
    op.create_table('event_topics',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_event_topics_name'), 'event_topics', ['name'], unique=True)
    op.create_index(op.f('ix_event_topics_status'), 'event_topics', ['status'], unique=False)
    # ### 自动生成结束 ###


def downgrade() -> None:
    # ### 自动生成开始：回滚业务表 ###
    op.drop_index(op.f('ix_event_topics_status'), table_name='event_topics')
    op.drop_index(op.f('ix_event_topics_name'), table_name='event_topics')
    op.drop_table('event_topics')
    op.drop_index(op.f('ix_event_subscriptions_topic_id'), table_name='event_subscriptions')
    op.drop_index(op.f('ix_event_subscriptions_subscriber_name'), table_name='event_subscriptions')
    op.drop_index(op.f('ix_event_subscriptions_status'), table_name='event_subscriptions')
    op.drop_table('event_subscriptions')
    op.drop_index(op.f('ix_event_messages_topic_id'), table_name='event_messages')
    op.drop_index(op.f('ix_event_messages_status'), table_name='event_messages')
    op.drop_table('event_messages')
    # ### 自动生成结束 ###
