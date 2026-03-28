package com.yupi.yuaicodemother.agent.service;

import com.mybatisflex.core.service.IService;
import com.yupi.yuaicodemother.agent.model.dto.AgentThreadCreateRequest;
import com.yupi.yuaicodemother.agent.model.entity.AgentThread;
import com.yupi.yuaicodemother.agent.model.vo.AgentThreadVO;
import com.yupi.yuaicodemother.model.entity.User;

import java.util.List;

public interface AgentThreadService extends IService<AgentThread> {

    AgentThread createThread(AgentThreadCreateRequest request, User loginUser);

    List<AgentThreadVO> listThreads(Long appId, User loginUser);

    AgentThread getOwnedThread(Long threadId, User loginUser);

    boolean archiveThread(Long threadId, User loginUser);

    AgentThread fillThreadTitleIfBlank(AgentThread thread, String firstMessage);
}
