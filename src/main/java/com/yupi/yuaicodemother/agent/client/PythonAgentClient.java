package com.yupi.yuaicodemother.agent.client;

import com.yupi.yuaicodemother.agent.client.dto.PythonChatStreamRequest;
import com.yupi.yuaicodemother.agent.client.dto.PythonSseEnvelope;
import java.util.Map;
import reactor.core.publisher.Flux;

public interface PythonAgentClient {

    Flux<PythonSseEnvelope> streamChat(PythonChatStreamRequest request);

    Map<String, Object> getInternalJson(String path, Map<String, Object> queryParams);

    Map<String, Object> postInternalJson(String path, Object body);
}
