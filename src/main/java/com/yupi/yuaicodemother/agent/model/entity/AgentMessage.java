package com.yupi.yuaicodemother.agent.model.entity;

import com.mybatisflex.annotation.Column;
import com.mybatisflex.annotation.Id;
import com.mybatisflex.annotation.KeyType;
import com.mybatisflex.annotation.Table;
import com.mybatisflex.core.keygen.KeyGenerators;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.io.Serial;
import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * Agent message entity.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Table("agent_message")
public class AgentMessage implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    /**
     * Id.
     */
    @Id(keyType = KeyType.Generator, value = KeyGenerators.snowFlakeId)
    private Long id;

    /**
     * Thread id.
     */
    @Column("thread_id")
    private Long threadId;

    /**
     * Turn id.
     */
    @Column("turn_id")
    private String turnId;

    /**
     * Message role.
     */
    private String role;

    /**
     * Event type.
     */
    @Column("event_type")
    private String eventType;

    /**
     * Message content.
     */
    @Column("content_text")
    private String contentText;

    /**
     * Event payload JSON.
     */
    @Column("payload_json")
    private String payloadJson;

    /**
     * Sequence number.
     */
    private Integer seq;

    /**
     * Create time.
     */
    @Column("create_time")
    private LocalDateTime createTime;

    /**
     * Update time.
     */
    @Column("update_time")
    private LocalDateTime updateTime;

    /**
     * Logic delete flag.
     */
    @Column(value = "is_delete", isLogicDelete = true)
    private Integer isDelete;
}
