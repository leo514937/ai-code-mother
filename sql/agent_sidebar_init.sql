-- Agent sidebar schema initialization
-- This script is intentionally isolated from the existing chat_history flow.

create table if not exists agent_thread
(
    id                bigint auto_increment comment 'id' primary key,
    app_id            bigint                                 not null comment 'app id',
    user_id           bigint                                 not null comment 'user id',
    title             varchar(255)                           null comment 'thread title',
    python_session_id varchar(128)                           not null comment 'python session id',
    status            varchar(32)  default 'ACTIVE'          not null comment 'thread status',
    last_message_at   datetime                               null comment 'last message time',
    create_time       datetime     default CURRENT_TIMESTAMP not null comment 'create time',
    update_time       datetime     default CURRENT_TIMESTAMP not null on update CURRENT_TIMESTAMP comment 'update time',
    is_delete         tinyint      default 0                 not null comment 'is deleted',
    unique key uk_python_session_id (python_session_id),
    index idx_user_id_app_id_status (user_id, app_id, status),
    index idx_user_id_app_id_last_message_at (user_id, app_id, last_message_at)
) comment 'agent thread' collate = utf8mb4_unicode_ci;

create table if not exists agent_message
(
    id           bigint auto_increment comment 'id' primary key,
    thread_id    bigint                                 not null comment 'thread id',
    turn_id      varchar(64)                            null comment 'turn id',
    role         varchar(32)                            not null comment 'message role',
    event_type   varchar(64)                            null comment 'event type',
    content_text text                                   null comment 'message content',
    payload_json longtext                               null comment 'event payload json',
    seq          int          default 0                 not null comment 'event sequence',
    create_time  datetime     default CURRENT_TIMESTAMP not null comment 'create time',
    update_time  datetime     default CURRENT_TIMESTAMP not null on update CURRENT_TIMESTAMP comment 'update time',
    is_delete    tinyint      default 0                 not null comment 'is deleted',
    unique key uk_thread_id_seq (thread_id, seq),
    index idx_thread_id_turn_id (thread_id, turn_id),
    index idx_thread_id_create_time (thread_id, create_time)
) comment 'agent message' collate = utf8mb4_unicode_ci;

create table if not exists agent_turn_audit
(
    id           bigint auto_increment comment 'id' primary key,
    thread_id    bigint                                 not null comment 'thread id',
    trace_id     varchar(64)                            not null comment 'trace id',
    request_text text                                   null comment 'request text',
    status       varchar(32)                            not null comment 'audit status',
    error_code   varchar(64)                            null comment 'error code',
    latency_ms   bigint                                 null comment 'latency ms',
    metrics_json longtext                               null comment 'metrics json',
    create_time  datetime     default CURRENT_TIMESTAMP not null comment 'create time',
    unique key uk_trace_id (trace_id),
    index idx_thread_id_create_time (thread_id, create_time)
) comment 'agent turn audit' collate = utf8mb4_unicode_ci;
