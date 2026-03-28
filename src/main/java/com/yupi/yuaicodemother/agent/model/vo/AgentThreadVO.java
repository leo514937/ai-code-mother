package com.yupi.yuaicodemother.agent.model.vo;

import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * Agent thread view object.
 */
@Data
public class AgentThreadVO implements Serializable {

    /**
     * Id.
     */
    private Long id;

    /**
     * Application id.
     */
    private Long appId;

    /**
     * User id.
     */
    private Long userId;

    /**
     * Thread title.
     */
    private String title;

    /**
     * Python session id.
     */
    private String pythonSessionId;

    /**
     * Thread status.
     */
    private String status;

    /**
     * Last message time.
     */
    private LocalDateTime lastMessageAt;

    /**
     * Create time.
     */
    private LocalDateTime createTime;

    /**
     * Update time.
     */
    private LocalDateTime updateTime;

    private static final long serialVersionUID = 1L;
}
