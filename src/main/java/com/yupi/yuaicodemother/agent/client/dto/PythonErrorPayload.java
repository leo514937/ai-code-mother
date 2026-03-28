package com.yupi.yuaicodemother.agent.client.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.LinkedHashMap;
import java.util.Map;
import lombok.Data;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class PythonErrorPayload {

    private String code;

    private String message;

    private String stage;

    private Boolean retryable;

    @JsonProperty("degraded_to")
    private String degradedTo;

    private Object detail;

    private Map<String, Object> details = new LinkedHashMap<>();
}
