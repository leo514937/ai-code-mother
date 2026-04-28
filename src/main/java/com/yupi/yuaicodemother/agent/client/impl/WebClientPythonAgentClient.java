package com.yupi.yuaicodemother.agent.client.impl;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.yupi.yuaicodemother.agent.client.PythonAgentClient;
import com.yupi.yuaicodemother.agent.client.dto.PythonChatStreamRequest;
import com.yupi.yuaicodemother.agent.client.dto.PythonErrorPayload;
import com.yupi.yuaicodemother.agent.client.dto.PythonSseEnvelope;
import com.yupi.yuaicodemother.agent.config.AgentFeatureProperties;
import com.yupi.yuaicodemother.agent.exception.PythonAgentInvokeException;
import com.yupi.yuaicodemother.agent.exception.PythonAgentProtocolException;
import com.yupi.yuaicodemother.agent.exception.PythonAgentTimeoutException;
import io.netty.channel.ConnectTimeoutException;
import io.netty.handler.timeout.ReadTimeoutException;
import java.net.SocketTimeoutException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.TimeoutException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Flux;

@Component
public class WebClientPythonAgentClient implements PythonAgentClient {

    private static final String CHAT_STREAM_PATH = "/internal/v1/chat/stream";

    private static final String FEEDBACK_REPORT_PATH = "/internal/v1/feedback/report";

    private static final String FEEDBACK_SAMPLES_PATH = "/internal/v1/feedback/samples";

    private static final String MEMORY_RECORDS_PATH = "/internal/v1/memory/records";

    private static final String MEMORY_CANDIDATES_PATH = "/internal/v1/memory/candidates";

    private static final String MEMORY_TRACES_PATH = "/internal/v1/memory/traces";

    private static final String MEMORY_DELETION_JOBS_PATH = "/internal/v1/memory/deletion-jobs";

    private static final String INTERNAL_TOKEN_HEADER = "X-Internal-Token";

    private static final String TRACE_ID_HEADER = "X-Trace-Id";

    private final WebClient agentWebClient;

    private final AgentFeatureProperties agentFeatureProperties;

    private final ObjectMapper objectMapper;

    public WebClientPythonAgentClient(
            @Qualifier("agentWebClient") WebClient agentWebClient,
            AgentFeatureProperties agentFeatureProperties,
            ObjectMapper objectMapper) {
        this.agentWebClient = agentWebClient;
        this.agentFeatureProperties = agentFeatureProperties;
        this.objectMapper = objectMapper;
    }

    @Override
    public Flux<PythonSseEnvelope> streamChat(PythonChatStreamRequest request) {
        return agentWebClient.post()
                .uri(CHAT_STREAM_PATH)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .headers(headers -> applyHeaders(headers, request))
                .bodyValue(request)
                .retrieve()
                .onStatus(HttpStatusCode::isError, response -> response.bodyToMono(String.class)
                        .defaultIfEmpty("")
                        .map(body -> buildInvokeException(response.statusCode(), body)))
                .bodyToFlux(new ParameterizedTypeReference<ServerSentEvent<String>>() {
                })
                .map(ServerSentEvent::data)
                .filter(StringUtils::hasText)
                .map(this::deserializeEnvelope)
                .onErrorMap(this::mapClientException);
    }

    @Override
    public Map<String, Object> getInternalJson(String path, Map<String, Object> queryParams) {
        Map<String, Object> params = queryParams == null ? Map.of() : queryParams;
        Map<String, Object> response = agentWebClient.get()
                .uri(uriBuilder -> {
                    var builder = uriBuilder.path(path);
                    for (Map.Entry<String, Object> entry : params.entrySet()) {
                        if (entry.getValue() != null) {
                            builder = builder.queryParam(entry.getKey(), entry.getValue());
                        }
                    }
                    return builder.build();
                })
                .headers(this::applyInternalTokenHeader)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .onStatus(HttpStatusCode::isError, responseMono -> responseMono.bodyToMono(String.class)
                        .defaultIfEmpty("")
                        .map(body -> buildInvokeException(responseMono.statusCode(), body)))
                .bodyToMono(new ParameterizedTypeReference<Map<String, Object>>() {
                })
                .block();
        return response == null ? new LinkedHashMap<>() : response;
    }

    @Override
    public Map<String, Object> postInternalJson(String path, Object body) {
        Map<String, Object> response = agentWebClient.post()
                .uri(path)
                .headers(this::applyInternalTokenHeader)
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(body == null ? Map.of() : body)
                .retrieve()
                .onStatus(HttpStatusCode::isError, responseMono -> responseMono.bodyToMono(String.class)
                        .defaultIfEmpty("")
                        .map(inner -> buildInvokeException(responseMono.statusCode(), inner)))
                .bodyToMono(new ParameterizedTypeReference<Map<String, Object>>() {
                })
                .block();
        return response == null ? new LinkedHashMap<>() : response;
    }

    private void applyHeaders(HttpHeaders headers, PythonChatStreamRequest request) {
        applyInternalTokenHeader(headers);
        if (StringUtils.hasText(request.getTraceId())) {
            headers.set(TRACE_ID_HEADER, request.getTraceId());
        }
    }

    private void applyInternalTokenHeader(HttpHeaders headers) {
        String internalToken = agentFeatureProperties.getPython().getInternalToken();
        if (StringUtils.hasText(internalToken)) {
            headers.set(INTERNAL_TOKEN_HEADER, internalToken);
        }
    }

    private PythonSseEnvelope deserializeEnvelope(String rawData) {
        try {
            return objectMapper.readValue(rawData, PythonSseEnvelope.class);
        } catch (JsonProcessingException e) {
            throw new PythonAgentProtocolException("Failed to decode Python agent SSE payload", e);
        }
    }

    private Throwable mapClientException(Throwable throwable) {
        if (throwable instanceof PythonAgentInvokeException) {
            return throwable;
        }
        if (throwable instanceof WebClientResponseException) {
            WebClientResponseException responseException = (WebClientResponseException) throwable;
            return buildInvokeException(responseException.getStatusCode(), responseException.getResponseBodyAsString());
        }
        if (throwable instanceof WebClientRequestException) {
            WebClientRequestException requestException = (WebClientRequestException) throwable;
            if (isTimeout(requestException)) {
                return new PythonAgentTimeoutException("Timed out while calling Python agent service", requestException);
            }
            return new PythonAgentInvokeException("Failed to connect to Python agent service", requestException);
        }
        if (isTimeout(throwable)) {
            return new PythonAgentTimeoutException("Timed out while reading Python agent response", throwable);
        }
        return new PythonAgentInvokeException("Unexpected error while invoking Python agent service", throwable);
    }

    private PythonAgentInvokeException buildInvokeException(HttpStatusCode statusCode, String responseBody) {
        String errorMessage = extractErrorMessage(responseBody);
        StringBuilder builder = new StringBuilder("Python agent service returned HTTP ")
                .append(statusCode.value());
        if (StringUtils.hasText(errorMessage)) {
            builder.append(": ").append(errorMessage);
        }
        return new PythonAgentInvokeException(builder.toString());
    }

    private String extractErrorMessage(String responseBody) {
        if (!StringUtils.hasText(responseBody)) {
            return "";
        }
        try {
            PythonErrorPayload payload = objectMapper.readValue(responseBody, PythonErrorPayload.class);
            Object detail = payload.getDetail();
            if (detail instanceof Map<?, ?>) {
                Map<?, ?> detailMap = (Map<?, ?>) detail;
                PythonErrorPayload nestedPayload = objectMapper.convertValue(detailMap, PythonErrorPayload.class);
                String nestedMessage = formatErrorPayload(nestedPayload);
                if (StringUtils.hasText(nestedMessage)) {
                    return nestedMessage;
                }
            }
            if (detail instanceof String) {
                String detailMessage = (String) detail;
                if (StringUtils.hasText(detailMessage)) {
                return detailMessage;
                }
            }
            String payloadMessage = formatErrorPayload(payload);
            if (StringUtils.hasText(payloadMessage)) {
                return payloadMessage;
            }
        } catch (IllegalArgumentException | JsonProcessingException ignored) {
            return responseBody;
        }
        return responseBody;
    }

    private String formatErrorPayload(PythonErrorPayload payload) {
        if (payload == null) {
            return "";
        }
        boolean hasCode = StringUtils.hasText(payload.getCode());
        boolean hasMessage = StringUtils.hasText(payload.getMessage());
        if (hasCode && hasMessage) {
            return payload.getCode() + ": " + payload.getMessage();
        }
        if (hasMessage) {
            return payload.getMessage();
        }
        if (hasCode) {
            return payload.getCode();
        }
        if (!payload.getDetails().isEmpty()) {
            return payload.getDetails().toString();
        }
        return "";
    }

    private boolean isTimeout(Throwable throwable) {
        Throwable current = throwable;
        while (current != null) {
            if (current instanceof TimeoutException
                    || current instanceof SocketTimeoutException
                    || current instanceof ReadTimeoutException
                    || current instanceof ConnectTimeoutException) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }
}
