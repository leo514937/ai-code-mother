package com.yupi.yuaicodemother.agent.service;

import com.yupi.yuaicodemother.agent.model.dto.AgentFeedbackRequest;
import com.yupi.yuaicodemother.agent.model.dto.AgentMemoryActionRequest;
import com.yupi.yuaicodemother.agent.model.entity.AgentThread;
import com.yupi.yuaicodemother.model.entity.User;
import org.springframework.http.codec.ServerSentEvent;
import reactor.core.publisher.Flux;

import java.util.Map;

public interface AgentGatewayService {

    Flux<ServerSentEvent<String>> streamMessage(Long threadId, String content, User loginUser);

    Map<String, Object> reportFeedback(AgentThread thread, User loginUser, AgentFeedbackRequest request);

    Map<String, Object> listMemoryRecords(AgentThread thread, User loginUser, String scope, String query, int limit);

    Map<String, Object> getMemoryRecord(AgentThread thread, User loginUser, String memoryId);

    Map<String, Object> listMemoryCandidates(AgentThread thread, User loginUser, int limit);

    Map<String, Object> listMemoryTraces(AgentThread thread, User loginUser, String sessionId, String turnId, int limit);

    Map<String, Object> getMemoryTrace(AgentThread thread, User loginUser, String traceId);

    Map<String, Object> listMemoryAccessLogs(AgentThread thread, User loginUser, String memoryId);

    Map<String, Object> listMemoryDeletionJobs(AgentThread thread, User loginUser, int limit);

    Map<String, Object> confirmMemoryCandidate(AgentThread thread, User loginUser, String candidateId, AgentMemoryActionRequest request);

    Map<String, Object> rejectMemoryCandidate(AgentThread thread, User loginUser, String candidateId, AgentMemoryActionRequest request);

    Map<String, Object> supersedeMemoryRecord(AgentThread thread, User loginUser, String memoryId, AgentMemoryActionRequest request);

    Map<String, Object> deleteMemoryRecord(AgentThread thread, User loginUser, String memoryId, AgentMemoryActionRequest request);
}
