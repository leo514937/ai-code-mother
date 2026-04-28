package com.yupi.yuaicodemother.agent.convert;

import com.yupi.yuaicodemother.agent.client.dto.PythonSseEnvelope;
import com.yupi.yuaicodemother.agent.model.vo.AgentSseEventVO;
import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.Test;

import java.time.OffsetDateTime;
import java.util.Map;

class PythonAgentEventConverterTest {

    private final PythonAgentEventConverter converter = new PythonAgentEventConverter();

    @Test
    void fromPythonEnvelopeShouldPreserveSessionAndWorkflowMetadata() {
        PythonSseEnvelope envelope = new PythonSseEnvelope();
        envelope.setEventType("final");
        envelope.setTraceId("trace-1");
        envelope.setSessionId("session-1");
        envelope.setTurnId("turn-1");
        envelope.setWorkflowVersion("learn-agent/v2");
        envelope.setTimestamp(OffsetDateTime.parse("2026-04-27T10:15:30+08:00"));
        envelope.setPayload(Map.of("answer_text", "ok"));

        AgentSseEventVO eventVO = converter.fromPythonEnvelope(123L, envelope);

        Assertions.assertEquals("session-1", eventVO.getSessionId());
        Assertions.assertEquals("learn-agent/v2", eventVO.getWorkflowVersion());
        Assertions.assertEquals("trace-1", eventVO.getTraceId());
        Assertions.assertEquals("turn-1", eventVO.getTurnId());
    }
}
