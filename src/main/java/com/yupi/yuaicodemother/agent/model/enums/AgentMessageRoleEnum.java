package com.yupi.yuaicodemother.agent.model.enums;

import cn.hutool.core.util.ObjUtil;
import lombok.Getter;

/**
 * Agent message role.
 */
@Getter
public enum AgentMessageRoleEnum {

    USER("User", "USER"),
    ASSISTANT("Assistant", "ASSISTANT"),
    SYSTEM("System", "SYSTEM");

    private final String text;

    private final String value;

    AgentMessageRoleEnum(String text, String value) {
        this.text = text;
        this.value = value;
    }

    /**
     * Get enum by value.
     *
     * @param value enum value
     * @return matched enum
     */
    public static AgentMessageRoleEnum getEnumByValue(String value) {
        if (ObjUtil.isEmpty(value)) {
            return null;
        }
        for (AgentMessageRoleEnum anEnum : AgentMessageRoleEnum.values()) {
            if (anEnum.value.equals(value)) {
                return anEnum;
            }
        }
        return null;
    }
}
