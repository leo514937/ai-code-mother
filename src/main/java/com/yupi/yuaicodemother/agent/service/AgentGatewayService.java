package com.yupi.yuaicodemother.agent.service;

import com.yupi.yuaicodemother.model.entity.User;
import org.springframework.http.codec.ServerSentEvent;
import reactor.core.publisher.Flux;

public interface AgentGatewayService {

    Flux<ServerSentEvent<String>> streamMessage(Long threadId, String content, User loginUser);
}
