package com.yupi.yuaicodemother.agent.model.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_EMPTY)
public class AgentMemoryActionRequest {

    private String reason;

    @JsonProperty("superseded_by")
    private String supersededBy;

    @JsonProperty("target_memory_id")
    private String targetMemoryId;
}
