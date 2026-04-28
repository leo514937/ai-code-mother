package com.yupi.yuaicodemother.agent.convert;

import cn.hutool.core.bean.BeanUtil;
import cn.hutool.json.JSONUtil;
import com.yupi.yuaicodemother.agent.client.dto.PythonSseEnvelope;
import com.yupi.yuaicodemother.agent.model.vo.AgentSseEventVO;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;

import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.LinkedHashMap;
import java.util.Map;

@Component
public class PythonAgentEventConverter {

    public AgentSseEventVO fromPythonEnvelope(Long threadId, PythonSseEnvelope envelope) {
        AgentSseEventVO eventVO = new AgentSseEventVO();
        eventVO.setEventType(envelope.getEventType());
        eventVO.setThreadId(threadId);
        eventVO.setTurnId(envelope.getTurnId());
        eventVO.setTraceId(envelope.getTraceId());
        eventVO.setSessionId(envelope.getSessionId());
        eventVO.setWorkflowVersion(envelope.getWorkflowVersion());
        eventVO.setTimestamp(toLocalDateTime(envelope.getTimestamp()));
        eventVO.setPayload(envelope.getPayload());
        return eventVO;
    }

    public AgentSseEventVO buildEvent(Long threadId, String turnId, String traceId, String eventType, Object payload) {
        AgentSseEventVO eventVO = new AgentSseEventVO();
        eventVO.setEventType(eventType);
        eventVO.setThreadId(threadId);
        eventVO.setTurnId(turnId);
        eventVO.setTraceId(traceId);
        eventVO.setSessionId(null);
        eventVO.setWorkflowVersion(null);
        eventVO.setTimestamp(LocalDateTime.now());
        eventVO.setPayload(payload);
        return eventVO;
    }

    public ServerSentEvent<String> toServerSentEvent(AgentSseEventVO eventVO) {
        return ServerSentEvent.<String>builder()
                .event(eventVO.getEventType())
                .data(JSONUtil.toJsonStr(eventVO))
                .build();
    }

    public Map<String, Object> buildErrorPayload(String code, String message) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("error", true);
        payload.put("code", code);
        payload.put("message", message);
        return payload;
    }

    public <T> T convertPayload(Object payload, Class<T> clazz) {
        if (payload == null) {
            return null;
        }
        if (clazz.isInstance(payload)) {
            return clazz.cast(payload);
        }
        return BeanUtil.toBean(payload, clazz);
    }

    private LocalDateTime toLocalDateTime(OffsetDateTime offsetDateTime) {
        if (offsetDateTime == null) {
            return LocalDateTime.now();
        }
        return offsetDateTime.atZoneSameInstant(ZoneId.systemDefault()).toLocalDateTime();
    }
}
