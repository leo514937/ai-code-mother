package com.yupi.yuaicodemother.agent.model.vo;

import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * Agent SSE event view object.
 */
@Data
public class AgentSseEventVO implements Serializable {

    /**
     * Event type.
     */
    private String eventType;

    /**
     * Thread id.
     */
    private Long threadId;

    /**
     * Turn id.
     */
    private String turnId;

    /**
     * Trace id.
     */
    private String traceId;

    /**
     * Python session id.
     */
    private String sessionId;

    /**
     * Workflow version.
     */
    private String workflowVersion;

    /**
     * Event time.
     */
    private LocalDateTime timestamp;

    /**
     * Event payload.
     */
    private Object payload;

    private static final long serialVersionUID = 1L;
}
