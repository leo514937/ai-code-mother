package com.yupi.yuaicodemother.agent.model.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
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
public class AgentFeedbackRequest {

    @JsonProperty("turn_id")
    private String turnId;

    @JsonProperty("trace_id")
    private String traceId;

    @JsonProperty("issue_type")
    private String issueType;

    @JsonProperty("is_helpful")
    private Boolean isHelpful;

    private String comment;

    @Builder.Default
    @JsonProperty("final_payload")
    private Map<String, Object> finalPayload = new LinkedHashMap<>();

    @Builder.Default
    private List<Map<String, Object>> timeline = List.of();

    @Builder.Default
    @JsonProperty("retrieval_summary")
    private Map<String, Object> retrievalSummary = new LinkedHashMap<>();

    @Builder.Default
    @JsonProperty("memory_used_summary")
    private Map<String, Object> memoryUsedSummary = new LinkedHashMap<>();

    @Builder.Default
    private Map<String, Object> context = new LinkedHashMap<>();
}
