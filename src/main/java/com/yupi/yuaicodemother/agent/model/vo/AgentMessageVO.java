package com.yupi.yuaicodemother.agent.model.vo;

import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * Agent message view object.
 */
@Data
public class AgentMessageVO implements Serializable {

    /**
     * Id.
     */
    private Long id;

    /**
     * Thread id.
     */
    private Long threadId;

    /**
     * Turn id.
     */
    private String turnId;

    /**
     * Role.
     */
    private String role;

    /**
     * Event type.
     */
    private String eventType;

    /**
     * Message content.
     */
    private String contentText;

    /**
     * Payload JSON.
     */
    private String payloadJson;

    /**
     * Sequence number.
     */
    private Integer seq;

    /**
     * Create time.
     */
    private LocalDateTime createTime;

    private static final long serialVersionUID = 1L;
}
