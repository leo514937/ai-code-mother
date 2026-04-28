package com.yupi.yuaicodemother.agent.model.enums;

import cn.hutool.core.util.ObjUtil;
import lombok.Getter;

/**
 * Agent event type.
 */
@Getter
public enum AgentEventTypeEnum {

    USER_MESSAGE("User Message", "user_message"),
    ACK("Ack", "ack"),
    RETRIEVAL_STARTED("Retrieval Started", "retrieval_started"),
    RETRIEVAL_RESULT("Retrieval Result", "retrieval_result"),
    MEMORY_RETRIEVAL_STARTED("Memory Retrieval Started", "memory_retrieval_started"),
    MEMORY_RETRIEVAL_RESULT("Memory Retrieval Result", "memory_retrieval_result"),
    MEMORY_PROMOTION_RESULT("Memory Promotion Result", "memory_promotion_result"),
    TOOL_CALL("Tool Call", "tool_call"),
    TOOL_RESULT("Tool Result", "tool_result"),
    CLARIFICATION_CARD("Clarification Card", "clarification_card"),
    PLAN_EXECUTION_STARTED("Plan Execution Started", "plan_execution_started"),
    PLAN_STEP_RESULT("Plan Step Result", "plan_step_result"),
    APPROVAL_REQUIRED("Approval Required", "approval_required"),
    PLAN_REPLANNED("Plan Replanned", "plan_replanned"),
    PLAN_EXECUTION_SUMMARY("Plan Execution Summary", "plan_execution_summary"),
    FINAL("Final", "final"),
    ASSISTANT("Assistant", "assistant"),
    ERROR("Error", "error");

    private final String text;

    private final String value;

    AgentEventTypeEnum(String text, String value) {
        this.text = text;
        this.value = value;
    }

    /**
     * Get enum by value.
     *
     * @param value enum value
     * @return matched enum
     */
    public static AgentEventTypeEnum getEnumByValue(String value) {
        if (ObjUtil.isEmpty(value)) {
            return null;
        }
        for (AgentEventTypeEnum anEnum : AgentEventTypeEnum.values()) {
            if (anEnum.value.equals(value)) {
                return anEnum;
            }
        }
        return null;
    }
}
