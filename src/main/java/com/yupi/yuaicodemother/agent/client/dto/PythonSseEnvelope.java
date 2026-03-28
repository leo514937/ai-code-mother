package com.yupi.yuaicodemother.agent.client.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.Map;
import lombok.Data;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class PythonSseEnvelope {

    @JsonProperty("event_type")
    private String eventType;

    @JsonProperty("trace_id")
    private String traceId;

    @JsonProperty("session_id")
    private String sessionId;

    @JsonProperty("turn_id")
    private String turnId;

    private OffsetDateTime timestamp;

    @JsonProperty("workflow_version")
    private String workflowVersion;

    private Map<String, Object> payload = new LinkedHashMap<>();
}
