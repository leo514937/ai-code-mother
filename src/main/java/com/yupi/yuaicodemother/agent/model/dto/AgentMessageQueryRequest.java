package com.yupi.yuaicodemother.agent.model.dto;

import com.yupi.yuaicodemother.common.PageRequest;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * Request for querying agent messages.
 */
@EqualsAndHashCode(callSuper = true)
@Data
public class AgentMessageQueryRequest extends PageRequest implements Serializable {

    /**
     * Thread id.
     */
    private Long threadId;

    /**
     * Cursor for history pagination.
     */
    private LocalDateTime lastCreateTime;

    private static final long serialVersionUID = 1L;
}
