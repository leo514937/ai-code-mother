package com.yupi.yuaicodemother.agent.service.impl;

import cn.hutool.core.util.StrUtil;
import cn.hutool.json.JSONUtil;
import com.yupi.yuaicodemother.agent.client.PythonAgentClient;
import com.yupi.yuaicodemother.agent.client.dto.PythonChatStreamRequest;
import com.yupi.yuaicodemother.agent.client.dto.PythonSseEnvelope;
import com.yupi.yuaicodemother.agent.convert.PythonAgentEventConverter;
import com.yupi.yuaicodemother.agent.exception.PythonAgentInvokeException;
import com.yupi.yuaicodemother.agent.exception.PythonAgentProtocolException;
import com.yupi.yuaicodemother.agent.exception.PythonAgentTimeoutException;
import com.yupi.yuaicodemother.agent.model.entity.AgentThread;
import com.yupi.yuaicodemother.agent.model.entity.AgentTurnAudit;
import com.yupi.yuaicodemother.agent.model.enums.AgentEventTypeEnum;
import com.yupi.yuaicodemother.agent.model.enums.AgentMessageRoleEnum;
import com.yupi.yuaicodemother.agent.model.enums.AgentThreadStatusEnum;
import com.yupi.yuaicodemother.agent.model.vo.AgentSseEventVO;
import com.yupi.yuaicodemother.agent.service.AgentGatewayService;
import com.yupi.yuaicodemother.agent.service.AgentMessageService;
import com.yupi.yuaicodemother.agent.service.AgentThreadService;
import com.yupi.yuaicodemother.exception.BusinessException;
import com.yupi.yuaicodemother.exception.ErrorCode;
import com.yupi.yuaicodemother.exception.ThrowUtils;
import com.yupi.yuaicodemother.mapper.agent.AgentTurnAuditMapper;
import com.yupi.yuaicodemother.model.entity.User;
import jakarta.annotation.Resource;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

@Service
public class AgentGatewayServiceImpl implements AgentGatewayService {

    @Resource
    private AgentThreadService agentThreadService;

    @Resource
    private AgentMessageService agentMessageService;

    @Resource
    private AgentTurnAuditMapper agentTurnAuditMapper;

    @Resource
    private PythonAgentClient pythonAgentClient;

    @Resource
    private PythonAgentEventConverter pythonAgentEventConverter;

    @Override
    public Flux<ServerSentEvent<String>> streamMessage(Long threadId, String content, User loginUser) {
        ThrowUtils.throwIf(StrUtil.isBlank(content), ErrorCode.PARAMS_ERROR, "Message content cannot be blank");
        AgentThread thread = agentThreadService.getOwnedThread(threadId, loginUser);
        ThrowUtils.throwIf(
                AgentThreadStatusEnum.ARCHIVED.getValue().equals(thread.getStatus()),
                ErrorCode.OPERATION_ERROR,
                "Archived thread cannot accept new messages"
        );

        Instant startTime = Instant.now();
        String normalizedContent = content.trim();
        String traceId = UUID.randomUUID().toString().replace("-", "");
        String turnId = UUID.randomUUID().toString().replace("-", "");
        AtomicInteger sequence = new AtomicInteger(agentMessageService.getNextSeq(threadId));
        AtomicBoolean terminalEventHandled = new AtomicBoolean(false);

        agentThreadService.fillThreadTitleIfBlank(thread, normalizedContent);
        agentMessageService.saveMessage(
                threadId,
                turnId,
                AgentMessageRoleEnum.USER.getValue(),
                AgentEventTypeEnum.USER_MESSAGE.getValue(),
                normalizedContent,
                null,
                sequence.incrementAndGet()
        );

        AgentTurnAudit audit = AgentTurnAudit.builder()
                .threadId(threadId)
                .traceId(traceId)
                .requestText(normalizedContent)
                .status("STARTED")
                .build();
        agentTurnAuditMapper.insert(audit);

        PythonChatStreamRequest pythonRequest = PythonChatStreamRequest.builder()
                .userId(String.valueOf(loginUser.getId()))
                .sessionId(thread.getPythonSessionId())
                .traceId(traceId)
                .turnId(turnId)
                .message(normalizedContent)
                .responseMode("detailed")
                .clientContext(buildClientContext(thread))
                .build();

        return pythonAgentClient.streamChat(pythonRequest)
                .map(envelope -> handlePythonEnvelope(thread, envelope, sequence, audit, startTime, terminalEventHandled))
                .map(pythonAgentEventConverter::toServerSentEvent)
                .doOnComplete(() -> finalizeOnComplete(thread, audit, startTime, terminalEventHandled))
                .onErrorResume(throwable -> handleStreamError(
                        threadId, turnId, traceId, audit, startTime, sequence, terminalEventHandled, throwable
                ));
    }

    private AgentSseEventVO handlePythonEnvelope(
            AgentThread thread,
            PythonSseEnvelope envelope,
            AtomicInteger sequence,
            AgentTurnAudit audit,
            Instant startTime,
            AtomicBoolean terminalEventHandled
    ) {
        AgentSseEventVO eventVO = pythonAgentEventConverter.fromPythonEnvelope(thread.getId(), envelope);
        agentMessageService.saveMessage(
                thread.getId(),
                StrUtil.blankToDefault(envelope.getTurnId(), eventVO.getTurnId()),
                AgentMessageRoleEnum.SYSTEM.getValue(),
                envelope.getEventType(),
                null,
                envelope.getPayload(),
                sequence.incrementAndGet()
        );
        thread.setLastMessageAt(LocalDateTime.now());
        agentThreadService.updateById(thread);

        if (AgentEventTypeEnum.FINAL.getValue().equals(envelope.getEventType())) {
            Object answerText = resolveFinalAnswer(envelope);
            if (answerText != null) {
                agentMessageService.saveMessage(
                        thread.getId(),
                        StrUtil.blankToDefault(envelope.getTurnId(), eventVO.getTurnId()),
                        AgentMessageRoleEnum.ASSISTANT.getValue(),
                        AgentEventTypeEnum.ASSISTANT.getValue(),
                        String.valueOf(answerText),
                        null,
                        sequence.incrementAndGet()
                );
            }
            if (terminalEventHandled.compareAndSet(false, true)) {
                updateAudit(audit, "SUCCESS", null, startTime, envelope.getPayload());
            }
        } else if (AgentEventTypeEnum.ERROR.getValue().equals(envelope.getEventType())) {
            if (terminalEventHandled.compareAndSet(false, true)) {
                String errorCode = envelope.getPayload() == null ? null : String.valueOf(envelope.getPayload().get("code"));
                updateAudit(audit, "FAILED", errorCode, startTime, envelope.getPayload());
            }
        }
        return eventVO;
    }

    private void finalizeOnComplete(
            AgentThread thread,
            AgentTurnAudit audit,
            Instant startTime,
            AtomicBoolean terminalEventHandled
    ) {
        if (terminalEventHandled.compareAndSet(false, true)) {
            thread.setLastMessageAt(LocalDateTime.now());
            agentThreadService.updateById(thread);
            updateAudit(audit, "SUCCESS", null, startTime, null);
        }
    }

    private Flux<ServerSentEvent<String>> handleStreamError(
            Long threadId,
            String turnId,
            String traceId,
            AgentTurnAudit audit,
            Instant startTime,
            AtomicInteger sequence,
            AtomicBoolean terminalEventHandled,
            Throwable throwable
    ) {
        if (!terminalEventHandled.compareAndSet(false, true)) {
            return Flux.empty();
        }
        String errorCode = resolveErrorCode(throwable);
        String errorMessage = resolveErrorMessage(throwable);
        Map<String, Object> payload = pythonAgentEventConverter.buildErrorPayload(errorCode, errorMessage);
        agentMessageService.saveMessage(
                threadId,
                turnId,
                AgentMessageRoleEnum.SYSTEM.getValue(),
                AgentEventTypeEnum.ERROR.getValue(),
                null,
                payload,
                sequence.incrementAndGet()
        );
        updateAudit(audit, "FAILED", errorCode, startTime, payload);
        AgentSseEventVO errorEvent = pythonAgentEventConverter.buildEvent(
                threadId,
                turnId,
                traceId,
                AgentEventTypeEnum.ERROR.getValue(),
                payload
        );
        return Flux.just(pythonAgentEventConverter.toServerSentEvent(errorEvent));
    }

    private void updateAudit(AgentTurnAudit audit, String status, String errorCode, Instant startTime, Object metricsPayload) {
        audit.setStatus(status);
        audit.setErrorCode(errorCode);
        audit.setLatencyMs(Duration.between(startTime, Instant.now()).toMillis());
        audit.setMetricsJson(metricsPayload == null ? null : JSONUtil.toJsonStr(metricsPayload));
        agentTurnAuditMapper.update(audit);
    }

    private Map<String, Object> buildClientContext(AgentThread thread) {
        Map<String, Object> clientContext = new LinkedHashMap<>();
        clientContext.put("channel", "knowledge_sidebar");
        clientContext.put("app_id", thread.getAppId());
        clientContext.put("thread_id", thread.getId());
        return clientContext;
    }

    private Object resolveFinalAnswer(PythonSseEnvelope envelope) {
        if (envelope.getPayload() == null || envelope.getPayload().isEmpty()) {
            return null;
        }
        Object answerText = envelope.getPayload().get("answer_text");
        if (answerText != null) {
            return answerText;
        }
        answerText = envelope.getPayload().get("answerText");
        if (answerText != null) {
            return answerText;
        }
        answerText = envelope.getPayload().get("answer");
        if (answerText != null) {
            return answerText;
        }
        answerText = envelope.getPayload().get("content");
        if (answerText != null) {
            return answerText;
        }
        return envelope.getPayload().get("text");
    }

    private String resolveErrorCode(Throwable throwable) {
        if (throwable instanceof BusinessException) {
            BusinessException businessException = (BusinessException) throwable;
            return String.valueOf(businessException.getCode());
        }
        if (throwable instanceof PythonAgentTimeoutException) {
            return "PYTHON_TIMEOUT";
        }
        if (throwable instanceof PythonAgentProtocolException) {
            return "PYTHON_PROTOCOL_ERROR";
        }
        if (throwable instanceof PythonAgentInvokeException) {
            return "PYTHON_INVOKE_ERROR";
        }
        return String.valueOf(ErrorCode.SYSTEM_ERROR.getCode());
    }

    private String resolveErrorMessage(Throwable throwable) {
        if (throwable instanceof BusinessException) {
            BusinessException businessException = (BusinessException) throwable;
            if (StrUtil.isNotBlank(businessException.getMessage())) {
                return businessException.getMessage();
            }
        }
        if (throwable != null && StrUtil.isNotBlank(throwable.getMessage())) {
            return throwable.getMessage();
        }
        return "Agent sidebar request failed";
    }
}
