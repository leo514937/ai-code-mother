package com.yupi.yuaicodemother.agent.service;

import com.mybatisflex.core.service.IService;
import com.yupi.yuaicodemother.agent.model.entity.AgentMessage;
import com.yupi.yuaicodemother.agent.model.vo.AgentMessageVO;

import java.time.LocalDateTime;
import java.util.List;

public interface AgentMessageService extends IService<AgentMessage> {

    List<AgentMessageVO> listThreadMessages(Long threadId, int pageSize, LocalDateTime lastCreateTime);

    int getNextSeq(Long threadId);

    AgentMessage saveMessage(
            Long threadId,
            String turnId,
            String role,
            String eventType,
            String contentText,
            Object payload,
            int seq
    );
}
