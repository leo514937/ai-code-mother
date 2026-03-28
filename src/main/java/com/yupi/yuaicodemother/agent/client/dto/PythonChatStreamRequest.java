package com.yupi.yuaicodemother.agent.client.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.LinkedHashMap;
import java.util.Map;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_EMPTY)
public class PythonChatStreamRequest {

    @JsonProperty("user_id")
    private String userId;

    @JsonProperty("session_id")
    private String sessionId;

    @JsonProperty("trace_id")
    private String traceId;

    private String message;

    @JsonProperty("turn_id")
    private String turnId;

    @JsonProperty("response_mode")
    private String responseMode;

    @JsonProperty("topic_hint")
    private String topicHint;

    @JsonProperty("history_summary")
    private String historySummary;

    @Builder.Default
    @JsonProperty("client_context")
    private Map<String, Object> clientContext = new LinkedHashMap<>();
}
