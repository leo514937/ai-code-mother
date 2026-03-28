package com.yupi.yuaicodemother.agent.model.dto;

import lombok.Data;

import java.io.Serializable;

/**
 * Request for creating an agent thread.
 */
@Data
public class AgentThreadCreateRequest implements Serializable {

    /**
     * Application id.
     */
    private Long appId;

    /**
     * Optional thread title.
     */
    private String title;

    private static final long serialVersionUID = 1L;
}
