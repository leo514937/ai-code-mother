package com.yupi.yuaicodemother.agent.model.enums;

import cn.hutool.core.util.ObjUtil;
import lombok.Getter;

/**
 * Agent thread status.
 */
@Getter
public enum AgentThreadStatusEnum {

    ACTIVE("Active", "ACTIVE"),
    ARCHIVED("Archived", "ARCHIVED");

    private final String text;

    private final String value;

    AgentThreadStatusEnum(String text, String value) {
        this.text = text;
        this.value = value;
    }

    /**
     * Get enum by value.
     *
     * @param value enum value
     * @return matched enum
     */
    public static AgentThreadStatusEnum getEnumByValue(String value) {
        if (ObjUtil.isEmpty(value)) {
            return null;
        }
        for (AgentThreadStatusEnum anEnum : AgentThreadStatusEnum.values()) {
            if (anEnum.value.equals(value)) {
                return anEnum;
            }
        }
        return null;
    }
}
