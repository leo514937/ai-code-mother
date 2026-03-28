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
 * Agent thread entity.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Table("agent_thread")
public class AgentThread implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    /**
     * Id.
     */
    @Id(keyType = KeyType.Generator, value = KeyGenerators.snowFlakeId)
    private Long id;

    /**
     * Application id.
     */
    @Column("app_id")
    private Long appId;

    /**
     * User id.
     */
    @Column("user_id")
    private Long userId;

    /**
     * Thread title.
     */
    private String title;

    /**
     * Python session id.
     */
    @Column("python_session_id")
    private String pythonSessionId;

    /**
     * Thread status.
     */
    private String status;

    /**
     * Last message time.
     */
    @Column("last_message_at")
    private LocalDateTime lastMessageAt;

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
