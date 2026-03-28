package com.yupi.yuaicodemother.agent.model.dto;

import lombok.Data;

import java.io.Serializable;

/**
 * Request for starting a new agent message stream.
 */
@Data
public class AgentMessageStreamRequest implements Serializable {

    /**
     * User message content.
     */
    private String content;

    private static final long serialVersionUID = 1L;
}
