package com.yupi.yuaicodemother.agent.client;

import com.yupi.yuaicodemother.agent.client.dto.PythonChatStreamRequest;
import com.yupi.yuaicodemother.agent.client.dto.PythonSseEnvelope;
import reactor.core.publisher.Flux;

public interface PythonAgentClient {

    Flux<PythonSseEnvelope> streamChat(PythonChatStreamRequest request);
}
