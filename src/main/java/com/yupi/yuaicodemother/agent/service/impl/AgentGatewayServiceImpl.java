package com.yupi.yuaicodemother.agent.service.impl;

import cn.hutool.core.util.StrUtil;
import cn.hutool.json.JSONUtil;
import com.yupi.yuaicodemother.agent.client.PythonAgentClient;
import com.yupi.yuaicodemother.agent.client.dto.PythonChatStreamRequest;
import com.yupi.yuaicodemother.agent.client.dto.PythonSseEnvelope;
import com.yupi.yuaicodemother.agent.model.dto.AgentFeedbackRequest;
import com.yupi.yuaicodemother.agent.model.dto.AgentMemoryActionRequest;
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

    @Override
    public Map<String, Object> reportFeedback(AgentThread thread, User loginUser, AgentFeedbackRequest request) {
        ThrowUtils.throwIf(thread == null, ErrorCode.PARAMS_ERROR, "Thread cannot be null");
        ThrowUtils.throwIf(request == null, ErrorCode.PARAMS_ERROR, "Feedback request cannot be null");
        return pythonAgentClient.postInternalJson("/internal/v1/feedback/report", buildFeedbackPayload(thread, loginUser, request));
    }

    @Override
    public Map<String, Object> listMemoryRecords(AgentThread thread, User loginUser, String scope, String query, int limit) {
        return pythonAgentClient.getInternalJson(
                "/internal/v1/memory/records",
                buildMemoryQuery(thread, loginUser, scope, query, limit)
        );
    }

    @Override
    public Map<String, Object> getMemoryRecord(AgentThread thread, User loginUser, String memoryId) {
        ThrowUtils.throwIf(StrUtil.isBlank(memoryId), ErrorCode.PARAMS_ERROR, "Memory id cannot be blank");
        return pythonAgentClient.getInternalJson(
                "/internal/v1/memory/records/" + memoryId,
                buildThreadQuery(thread, loginUser)
        );
    }

    @Override
    public Map<String, Object> listMemoryCandidates(AgentThread thread, User loginUser, int limit) {
        return pythonAgentClient.getInternalJson(
                "/internal/v1/memory/candidates",
                buildMemoryQuery(thread, loginUser, null, null, limit)
        );
    }

    @Override
    public Map<String, Object> listMemoryTraces(AgentThread thread, User loginUser, String sessionId, String turnId, int limit) {
        Map<String, Object> query = buildThreadQuery(thread, loginUser);
        query.put("session_id", StrUtil.blankToDefault(sessionId, thread.getPythonSessionId()));
        if (StrUtil.isNotBlank(turnId)) {
            query.put("turn_id", turnId);
        }
        query.put("limit", limit);
        return pythonAgentClient.getInternalJson("/internal/v1/memory/traces", query);
    }

    @Override
    public Map<String, Object> getMemoryTrace(AgentThread thread, User loginUser, String traceId) {
        ThrowUtils.throwIf(StrUtil.isBlank(traceId), ErrorCode.PARAMS_ERROR, "Trace id cannot be blank");
        return pythonAgentClient.getInternalJson(
                "/internal/v1/memory/traces/" + traceId,
                buildThreadQuery(thread, loginUser)
        );
    }

    @Override
    public Map<String, Object> listMemoryAccessLogs(AgentThread thread, User loginUser, String memoryId) {
        ThrowUtils.throwIf(StrUtil.isBlank(memoryId), ErrorCode.PARAMS_ERROR, "Memory id cannot be blank");
        return pythonAgentClient.getInternalJson(
                "/internal/v1/memory/records/" + memoryId + "/access-logs",
                buildThreadQuery(thread, loginUser)
        );
    }

    @Override
    public Map<String, Object> listMemoryDeletionJobs(AgentThread thread, User loginUser, int limit) {
        return pythonAgentClient.getInternalJson(
                "/internal/v1/memory/deletion-jobs",
                buildMemoryQuery(thread, loginUser, null, null, limit)
        );
    }

    @Override
    public Map<String, Object> confirmMemoryCandidate(AgentThread thread, User loginUser, String candidateId, AgentMemoryActionRequest request) {
        ThrowUtils.throwIf(StrUtil.isBlank(candidateId), ErrorCode.PARAMS_ERROR, "Candidate id cannot be blank");
        return pythonAgentClient.postInternalJson(
                "/internal/v1/memory/candidates/" + candidateId + "/confirm",
                buildMemoryActionPayload(thread, loginUser, request)
        );
    }

    @Override
    public Map<String, Object> rejectMemoryCandidate(AgentThread thread, User loginUser, String candidateId, AgentMemoryActionRequest request) {
        ThrowUtils.throwIf(StrUtil.isBlank(candidateId), ErrorCode.PARAMS_ERROR, "Candidate id cannot be blank");
        return pythonAgentClient.postInternalJson(
                "/internal/v1/memory/candidates/" + candidateId + "/reject",
                buildMemoryActionPayload(thread, loginUser, request)
        );
    }

    @Override
    public Map<String, Object> supersedeMemoryRecord(AgentThread thread, User loginUser, String memoryId, AgentMemoryActionRequest request) {
        ThrowUtils.throwIf(StrUtil.isBlank(memoryId), ErrorCode.PARAMS_ERROR, "Memory id cannot be blank");
        return pythonAgentClient.postInternalJson(
                "/internal/v1/memory/records/" + memoryId + "/supersede",
                buildMemoryActionPayload(thread, loginUser, request)
        );
    }

    @Override
    public Map<String, Object> deleteMemoryRecord(AgentThread thread, User loginUser, String memoryId, AgentMemoryActionRequest request) {
        ThrowUtils.throwIf(StrUtil.isBlank(memoryId), ErrorCode.PARAMS_ERROR, "Memory id cannot be blank");
        return pythonAgentClient.postInternalJson(
                "/internal/v1/memory/records/" + memoryId + "/delete",
                buildMemoryActionPayload(thread, loginUser, request)
        );
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

    private Map<String, Object> buildThreadQuery(AgentThread thread, User loginUser) {
        Map<String, Object> query = new LinkedHashMap<>();
        query.put("user_id", String.valueOf(loginUser.getId()));
        query.put("thread_id", String.valueOf(thread.getId()));
        query.put("session_id", thread.getPythonSessionId());
        return query;
    }

    private Map<String, Object> buildMemoryQuery(AgentThread thread, User loginUser, String scope, String queryText, int limit) {
        Map<String, Object> query = buildThreadQuery(thread, loginUser);
        if (StrUtil.isNotBlank(scope)) {
            query.put("scope", scope);
        }
        if (StrUtil.isNotBlank(queryText)) {
            query.put("query", queryText);
        }
        query.put("limit", limit);
        return query;
    }

    private Map<String, Object> buildMemoryActionPayload(AgentThread thread, User loginUser, AgentMemoryActionRequest request) {
        Map<String, Object> payload = buildThreadQuery(thread, loginUser);
        if (request == null) {
            return payload;
        }
        if (StrUtil.isNotBlank(request.getReason())) {
            payload.put("reason", request.getReason());
        }
        if (StrUtil.isNotBlank(request.getSupersededBy())) {
            payload.put("superseded_by", request.getSupersededBy());
        }
        if (StrUtil.isNotBlank(request.getTargetMemoryId())) {
            payload.put("target_memory_id", request.getTargetMemoryId());
        }
        return payload;
    }

    private Map<String, Object> buildFeedbackPayload(AgentThread thread, User loginUser, AgentFeedbackRequest request) {
        Map<String, Object> payload = buildThreadQuery(thread, loginUser);
        if (request.getTurnId() != null) {
            payload.put("turn_id", request.getTurnId());
        }
        if (request.getTraceId() != null) {
            payload.put("trace_id", request.getTraceId());
        }
        if (request.getIssueType() != null) {
            payload.put("issue_type", request.getIssueType());
        }
        payload.put("is_helpful", request.getIsHelpful());
        if (request.getComment() != null) {
            payload.put("comment", request.getComment());
        }
        payload.put("final_payload", request.getFinalPayload());
        payload.put("timeline", request.getTimeline());
        payload.put("retrieval_summary", request.getRetrievalSummary());
        payload.put("memory_used_summary", request.getMemoryUsedSummary());
        payload.put("context", request.getContext());
        return payload;
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
